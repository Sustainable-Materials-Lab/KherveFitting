"""
VGD File Import Module for KherveFitting
Thermo Scientific / VG Scienta Binary Format (OLE2 Compound File)

VGD files store single XPS core level scans in Microsoft Compound File format.
Data is stored as Kinetic Energy and converted to Binding Energy using: BE = Source_Energy - KE
"""

import os
import struct
import numpy as np
import openpyxl
import wx
import json
import re

try:
    import olefile
except ImportError:
    olefile = None


def extract_core_level_name(filename):
    """
    Extract clean core level name from filename.

    Examples:
        'O1s_Scan.VGD' -> 'O1s'
        'O1s Scan.VGD' -> 'O1s'
        'Sr3d Scan.VGD' -> 'Sr3d'
        'Ni2p core level.VGD' -> 'Ni2p'
        'C1s_Region.VGD' -> 'C1s'
    """
    base_name = os.path.splitext(filename)[0]

    # Remove common suffixes (case insensitive)
    suffixes_to_remove = [
        '_Scan', '_scan', '_SCAN',
        ' Scan', ' scan', ' SCAN',
        '_Region', '_region', '_REGION',
        ' Region', ' region', ' REGION',
        '_core level', '_Core Level', '_Core level',
        ' core level', ' Core Level', ' Core level',
        '_spectrum', '_Spectrum', ' spectrum', ' Spectrum'
    ]

    result = base_name
    for suffix in suffixes_to_remove:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
            break

    # Also try regex to catch variations like "O1s scan" or "Ni2p_scan"
    # Pattern: element + orbital at the start, followed by separator and text
    match = re.match(r'^([A-Z][a-z]?\d+[spdfgh]\d*)[\s_]', result + ' ')
    if match:
        result = match.group(1)

    return result.strip()


def parse_vgd_file(file_path):
    """
    Parse a VGD file and return extracted data.

    Returns:
        dict with keys: intensities, ke_start, ke_step, num_points, source_energy,
                       txf_coeffs, pass_energy, work_fn, dwell_time, metadata
    """
    if olefile is None:
        raise ImportError("olefile library is required")

    ole = olefile.OleFileIO(file_path)

    # Get metadata from OLE properties
    metadata = ole.get_metadata()
    title = metadata.title.split('\x00')[0] if metadata.title else "Unknown"
    subject = metadata.subject.split('\x00')[0] if metadata.subject else ""
    author = metadata.author.split('\x00')[0] if metadata.author else ""
    create_time = str(metadata.create_time) if metadata.create_time else ""
    saved_time = str(metadata.last_saved_time) if metadata.last_saved_time else ""

    # Read intensity data from VGData stream
    vgdata = ole.openstream('VGData').read()
    num_points = len(vgdata) // 8

    intensities = []
    for i in range(num_points):
        val = struct.unpack('<d', vgdata[i*8:i*8+8])[0]
        intensities.append(val)

    # Extract KE range from VGSpaceAxes
    space_axes = ole.openstream('VGSpaceAxes').read()
    ke_start = struct.unpack('<d', space_axes[30:38])[0] if len(space_axes) >= 46 else None
    ke_step = struct.unpack('<d', space_axes[38:46])[0] if len(space_axes) >= 46 else None

    # Extract acquisition parameters from property stream
    prop_stream_name = '\x05Q5nw4m3lIjudbfwyAayojlptCa'
    prop_data = ole.openstream(prop_stream_name).read()

    # Extract X-ray source energy
    source_energy = None
    for i in range(0, len(prop_data)-4, 4):
        val = struct.unpack('<f', prop_data[i:i+4])[0]
        if 1480 < val < 1490:
            source_energy = val
            break
    if source_energy is None:
        source_energy = 1486.68

    # Extract Pass Energy and use its offset as reference for other parameters
    pass_energy = None
    pe_offset = None
    for i in range(0, len(prop_data) - 4, 4):
        val = struct.unpack('<f', prop_data[i:i + 4])[0]
        if val in [10.0, 20.0, 35.0, 50.0, 100.0, 160.0, 200.0]:
            pass_energy = val
            pe_offset = i
            break

    # Dwell Time is at PE offset + 8
    dwell_time = None
    if pe_offset and pe_offset + 12 <= len(prop_data):
        dwell_time = struct.unpack('<f', prop_data[pe_offset + 8:pe_offset + 12])[0]
        if not (0.001 < dwell_time < 10.0):  # Sanity check
            dwell_time = None

    # Periods is at PE offset - 32
    periods = None
    if pe_offset and pe_offset >= 32:
        periods = struct.unpack('<i', prop_data[pe_offset - 32:pe_offset - 28])[0]
        if not (1 <= periods <= 1000):  # Sanity check
            periods = None

    # Extract Work Function
    work_fn = None
    for i in range(0, len(prop_data)-4, 4):
        val = struct.unpack('<f', prop_data[i:i+4])[0]
        if 4.0 < val < 5.0:
            work_fn = val
            break

    # # Extract Dwell Time
    # dwell_time = None
    # for i in range(0, len(prop_data)-8, 4):
    #     if i+8 <= len(prop_data):
    #         val = struct.unpack('<d', prop_data[i:i+8])[0]
    #         if 0.01 < val < 1.0:
    #             dwell_time = val
    #             break

        # Extract Transmission Function coefficients
        # TXF coefficients are stored with 8-byte spacing (float + 4-byte padding)
        # First coefficient 'a' is typically 4.0-4.5
        txf_coeffs = []
        for start in range(3100, min(3300, len(prop_data) - 32), 4):
            val = struct.unpack('<f', prop_data[start:start + 4])[0]
            if 4.0 < val < 4.5:
                vals = []
                valid = True
                for j in range(4):
                    off = start + j * 8
                    if off + 4 <= len(prop_data):
                        v = struct.unpack('<f', prop_data[off:off + 4])[0]
                        vals.append(v)
                    else:
                        valid = False
                        break
                if valid and len(vals) == 4 and 0.5 < vals[1] < 1.0:
                    txf_coeffs = vals
                    break

    ole.close()

    return {
        'intensities': intensities,
        'ke_start': ke_start,
        'ke_step': ke_step,
        'num_points': num_points,
        'source_energy': source_energy,
        'txf_coeffs': txf_coeffs,
        'pass_energy': pass_energy,
        'work_fn': work_fn,
        'dwell_time': dwell_time,
        'periods': periods,
        'metadata': {
            'title': title,
            'subject': subject,
            'author': author,
            'create_time': create_time,
            'saved_time': saved_time
        }
    }


def calculate_vgd_data(parsed_data):
    """
    Calculate BE values, transmission, and corrected data from parsed VGD data.

    Returns:
        dict with keys: be_values, ke_values, transmission_values, corrected_data,
                       be_start, be_end, be_step
    """
    intensities = parsed_data['intensities']
    ke_start = parsed_data['ke_start']
    ke_step = parsed_data['ke_step']
    num_points = parsed_data['num_points']
    source_energy = parsed_data['source_energy']
    txf_coeffs = parsed_data['txf_coeffs']

    # Calculate KE values (increasing)
    ke_values = [ke_start + i * ke_step for i in range(num_points)]

    # Convert to BE (decreasing - high to low, correct for XPS)
    be_values = [source_energy - ke for ke in ke_values]

    be_start = be_values[0]
    be_end = be_values[-1]
    be_step = (be_end - be_start) / (num_points - 1) if num_points > 1 else 0

    # Calculate corrected data: Raw Data / (Periods * Dwell Time)
    dwell_time = parsed_data.get('dwell_time')
    periods = parsed_data.get('periods')
    txf_valid = True

    if dwell_time and periods and dwell_time > 0 and periods > 0:
        correction_factor = periods * dwell_time
        corrected_data = [intensity / correction_factor for intensity in intensities]
        transmission_values = [correction_factor] * num_points
    else:
        # No correction available
        corrected_data = intensities.copy()
        transmission_values = [1.0] * num_points

    return {
        'be_values': be_values,
        'ke_values': ke_values,
        'transmission_values': transmission_values,
        'corrected_data': corrected_data,
        'intensities': intensities,
        'be_start': be_start,
        'be_end': be_end,
        'be_step': be_step,
        'txf_valid': txf_valid
    }


def import_vgd_file(window, file_path=None, show_message=False):
    """
    Import Thermo VGD binary file (single core level).

    Args:
        window: Main KherveFitting window instance
        file_path: Path to .vgd file (if None, shows file dialog)
        show_message: If True, show success message box
    """
    if olefile is None:
        wx.MessageBox(
            "The 'olefile' library is required to import VGD files.\n\n"
            "Install it with:\n  pip install olefile",
            "Missing Library",
            wx.OK | wx.ICON_ERROR
        )
        return

    if file_path is None:
        with wx.FileDialog(window, "Open VGD file",
                          wildcard="VGD files (*.vgd;*.VGD)|*.vgd;*.VGD",
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            file_path = fileDialog.GetPath()

    try:
        # Parse VGD file
        parsed_data = parse_vgd_file(file_path)
        calc_data = calculate_vgd_data(parsed_data)

        # Extract core level name from filename
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        core_level = extract_core_level_name(os.path.basename(file_path))

        # Get metadata
        meta = parsed_data['metadata']
        source_energy = parsed_data['source_energy']
        source_label = "Al K-alpha Monochromated" if abs(source_energy - 1486.68) < 0.1 else f"X-ray {source_energy:.2f} eV"

        # Create Excel file with same name as VGD file
        output_dir = os.path.dirname(file_path)
        excel_path = os.path.join(output_dir, f"{base_name}.xlsx")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # Create data sheet
        sheet_name = f"{core_level}0"
        ws = wb.create_sheet(sheet_name)

        # Write headers
        ws.cell(row=1, column=1, value='B.E.')
        ws.cell(row=1, column=2, value='Corrected Data')
        ws.cell(row=1, column=3, value='Raw Data')
        ws.cell(row=1, column=4, value='Transmission')

        # Write data
        for i, (be, corr, raw, trans) in enumerate(zip(
                calc_data['be_values'],
                calc_data['corrected_data'],
                calc_data['intensities'],
                calc_data['transmission_values']), start=2):
            ws.cell(row=i, column=1, value=round(be, 2))
            ws.cell(row=i, column=2, value=round(corr, 2))
            ws.cell(row=i, column=3, value=round(raw, 2))
            ws.cell(row=i, column=4, value=round(trans, 2))

        # Add experimental info in column 50 (AX)
        exp_col = 50
        ws.cell(row=1, column=exp_col, value="Experimental Description")

        exp_metadata = {
            'Sample ID': meta['subject'] if meta['subject'] else base_name,
            'Title': meta['title'],
            'Author': meta['author'],
            'Date Created': meta['create_time'].split()[0] if meta['create_time'] else '',
            'Time Created': meta['create_time'].split()[1] if meta['create_time'] and len(meta['create_time'].split()) > 1 else '',
            'Date Saved': meta['saved_time'].split()[0] if meta['saved_time'] else '',
            'Time Saved': meta['saved_time'].split()[1] if meta['saved_time'] and len(meta['saved_time'].split()) > 1 else '',
            'Technique': 'XPS',
            'Species & Transition': core_level,
            'Source Label': source_label,
            'Source Energy': f"{source_energy:.2f}",
            'Pass Energy': f"{parsed_data['pass_energy']:.2f}" if parsed_data['pass_energy'] else 'Unknown',
            'Work Function': f"{parsed_data['work_fn']:.2f}" if parsed_data['work_fn'] else 'Unknown',
            'Dwell Time': f"{parsed_data['dwell_time']:.4f}" if parsed_data['dwell_time'] else 'Unknown',
            'Periods': str(parsed_data['periods']) if parsed_data['periods'] else 'Unknown',
            'Number of Points': str(parsed_data['num_points']),
            'BE Start': f"{calc_data['be_start']:.2f}",
            'BE End': f"{calc_data['be_end']:.2f}",
            'BE Step': f"{abs(calc_data['be_step']):.4f}",
            'KE Start': f"{parsed_data['ke_start']:.2f}" if parsed_data['ke_start'] else 'Unknown',
            'KE Step': f"{parsed_data['ke_step']:.4f}" if parsed_data['ke_step'] else 'Unknown',
            'TXF Applied': 'Yes' if calc_data['txf_valid'] else 'No',
            'TXF Coefficients': ', '.join([f"{c:.6f}" for c in parsed_data['txf_coeffs']]) if parsed_data['txf_coeffs'] else 'N/A',
        }

        row = 2
        for key, value in exp_metadata.items():
            ws.cell(row=row, column=exp_col, value=key)
            ws.cell(row=row, column=exp_col + 1, value=str(value))
            row += 1

        ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col)].width = 25
        ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col + 1)].width = 40

        wb.save(excel_path)

        # Import into KherveFitting
        from libraries.ConfigFile import Init_Measurement_Data, add_core_level_Data
        from libraries.FileMenu.Save import update_undo_redo_state, save_state, convert_to_serializable_and_round
        from libraries.Sheet_Operations import on_sheet_selected

        window.Data = Init_Measurement_Data(window)
        window.Data['FilePath'] = excel_path

        window.history = []
        window.redo_stack = []
        update_undo_redo_state(window)

        window.results_grid.ClearGrid()
        if window.results_grid.GetNumberRows() > 0:
            window.results_grid.DeleteRows(0, window.results_grid.GetNumberRows())

        add_core_level_Data(window.Data, window, excel_path, sheet_name)

        sample_name = meta['subject'] if meta['subject'] else base_name
        window.Data['SampleNames'] = {0: sample_name}

        json_path = excel_path.replace('.xlsx', '.json')
        serializable_data = convert_to_serializable_and_round(window.Data)
        with open(json_path, 'w') as f:
            json.dump(serializable_data, f, indent=4)

        window.sheet_combobox.Clear()
        window.sheet_combobox.Append(sheet_name)
        window.sheet_combobox.SetSelection(0)
        window.current_sheet = sheet_name

        on_sheet_selected(window, None)
        save_state(window)

        if show_message:
            wx.MessageBox(f"VGD file imported: {core_level}", "Import Successful", wx.OK | wx.ICON_INFORMATION)

    except Exception as e:
        import traceback
        traceback.print_exc()
        wx.MessageBox(f"Error importing VGD file:\n\n{str(e)}", "Error", wx.OK | wx.ICON_ERROR)


def import_multiple_vgd_files(window, file_paths=None, show_message=False):
    """
    Import multiple VGD files into a single Excel workbook.

    Args:
        window: Main KherveFitting window instance
        file_paths: List of paths to .vgd files (if None, shows file dialog)
        show_message: If True, show success message box
    """
    if olefile is None:
        wx.MessageBox(
            "The 'olefile' library is required to import VGD files.\n\n"
            "Install it with:\n  pip install olefile",
            "Missing Library",
            wx.OK | wx.ICON_ERROR
        )
        return

    if file_paths is None:
        with wx.FileDialog(window, "Select VGD files",
                          wildcard="VGD files (*.vgd;*.VGD)|*.vgd;*.VGD",
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            file_paths = fileDialog.GetPaths()

    if not file_paths:
        return

    try:
        # Use first file's directory and create combined filename
        output_dir = os.path.dirname(file_paths[0])
        first_base = os.path.splitext(os.path.basename(file_paths[0]))[0]

        # If multiple files, use a combined name
        if len(file_paths) > 1:
            excel_path = os.path.join(output_dir, f"{first_base}_combined.xlsx")
        else:
            excel_path = os.path.join(output_dir, f"{first_base}.xlsx")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        sheet_names = []
        first_sample_name = None

        for file_path in file_paths:
            try:
                parsed_data = parse_vgd_file(file_path)
                calc_data = calculate_vgd_data(parsed_data)

                base_name = os.path.splitext(os.path.basename(file_path))[0]
                core_level = extract_core_level_name(os.path.basename(file_path))

                meta = parsed_data['metadata']
                source_energy = parsed_data['source_energy']
                source_label = "Al K-alpha Monochromated" if abs(source_energy - 1486.68) < 0.1 else f"X-ray {source_energy:.2f} eV"

                if first_sample_name is None:
                    first_sample_name = meta['subject'] if meta['subject'] else base_name

                # Create unique sheet name
                sheet_name = f"{core_level}0"
                counter = 0
                while sheet_name in sheet_names:
                    counter += 1
                    sheet_name = f"{core_level}{counter}"
                sheet_names.append(sheet_name)

                ws = wb.create_sheet(sheet_name)

                # Write headers
                ws.cell(row=1, column=1, value='B.E.')
                ws.cell(row=1, column=2, value='Corrected Data')
                ws.cell(row=1, column=3, value='Raw Data')
                ws.cell(row=1, column=4, value='Transmission')

                # Write data
                for i, (be, corr, raw, trans) in enumerate(zip(
                        calc_data['be_values'],
                        calc_data['corrected_data'],
                        calc_data['intensities'],
                        calc_data['transmission_values']), start=2):
                    ws.cell(row=i, column=1, value=round(be, 2))
                    ws.cell(row=i, column=2, value=round(corr, 2))
                    ws.cell(row=i, column=3, value=round(raw, 2))
                    ws.cell(row=i, column=4, value=round(trans, 2))

                # Add experimental info
                exp_col = 50
                ws.cell(row=1, column=exp_col, value="Experimental Description")

                exp_metadata = {
                    'Sample ID': meta['subject'] if meta['subject'] else base_name,
                    'Title': meta['title'],
                    'Author': meta['author'],
                    'Date Created': meta['create_time'].split()[0] if meta['create_time'] else '',
                    'Time Created': meta['create_time'].split()[1] if meta['create_time'] and len(meta['create_time'].split()) > 1 else '',
                    'Date Saved': meta['saved_time'].split()[0] if meta['saved_time'] else '',
                    'Time Saved': meta['saved_time'].split()[1] if meta['saved_time'] and len(meta['saved_time'].split()) > 1 else '',
                    'Technique': 'XPS',
                    'Species & Transition': core_level,
                    'Source Label': source_label,
                    'Source Energy': f"{source_energy:.2f}",
                    'Pass Energy': f"{parsed_data['pass_energy']:.2f}" if parsed_data['pass_energy'] else 'Unknown',
                    'Work Function': f"{parsed_data['work_fn']:.2f}" if parsed_data['work_fn'] else 'Unknown',
                    'Dwell Time': f"{parsed_data['dwell_time']:.4f}" if parsed_data['dwell_time'] else 'Unknown',
                    'Periods': str(parsed_data['periods']) if parsed_data['periods'] else 'Unknown',
                    'Number of Points': str(parsed_data['num_points']),
                    'BE Start': f"{calc_data['be_start']:.2f}",
                    'BE End': f"{calc_data['be_end']:.2f}",
                    'BE Step': f"{abs(calc_data['be_step']):.4f}",
                    'KE Start': f"{parsed_data['ke_start']:.2f}" if parsed_data['ke_start'] else 'Unknown',
                    'KE Step': f"{parsed_data['ke_step']:.4f}" if parsed_data['ke_step'] else 'Unknown',
                    'TXF Applied': 'Yes' if calc_data['txf_valid'] else 'No',
                    'TXF Coefficients': ', '.join([f"{c:.6f}" for c in parsed_data['txf_coeffs']]) if parsed_data['txf_coeffs'] else 'N/A',
                }

                row = 2
                for key, value in exp_metadata.items():
                    ws.cell(row=row, column=exp_col, value=key)
                    ws.cell(row=row, column=exp_col + 1, value=str(value))
                    row += 1

                ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col)].width = 25
                ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col + 1)].width = 40

            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue

        if not sheet_names:
            wx.MessageBox("No VGD files could be processed", "Error", wx.OK | wx.ICON_ERROR)
            return

        wb.save(excel_path)

        # Import into KherveFitting
        from libraries.ConfigFile import Init_Measurement_Data, add_core_level_Data
        from libraries.FileMenu.Save import update_undo_redo_state, save_state, convert_to_serializable_and_round
        from libraries.Sheet_Operations import on_sheet_selected

        window.Data = Init_Measurement_Data(window)
        window.Data['FilePath'] = excel_path

        window.history = []
        window.redo_stack = []
        update_undo_redo_state(window)

        window.results_grid.ClearGrid()
        if window.results_grid.GetNumberRows() > 0:
            window.results_grid.DeleteRows(0, window.results_grid.GetNumberRows())

        # Add all core levels
        for sheet_name in sheet_names:
            add_core_level_Data(window.Data, window, excel_path, sheet_name)

        window.Data['SampleNames'] = {0: first_sample_name}

        json_path = excel_path.replace('.xlsx', '.json')
        serializable_data = convert_to_serializable_and_round(window.Data)
        with open(json_path, 'w') as f:
            json.dump(serializable_data, f, indent=4)

        # Update UI
        window.sheet_combobox.Clear()
        for sheet_name in sheet_names:
            window.sheet_combobox.Append(sheet_name)
        window.sheet_combobox.SetSelection(0)
        window.current_sheet = sheet_names[0]

        on_sheet_selected(window, None)
        save_state(window)

        if show_message:
            wx.MessageBox(f"Imported {len(sheet_names)} VGD files", "Import Successful", wx.OK | wx.ICON_INFORMATION)

    except Exception as e:
        import traceback
        traceback.print_exc()
        wx.MessageBox(f"Error importing VGD files:\n\n{str(e)}", "Error", wx.OK | wx.ICON_ERROR)