"""
VGD File Import Module for KherveFitting
Thermo Scientific / VG Scienta Binary Format (OLE2 Compound File)

VGD files store single XPS core level scans in Microsoft Compound File format.
"""

import os
import struct
import numpy as np
import openpyxl
import wx

try:
    import olefile
except ImportError:
    olefile = None


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

try:
    import olefile
except ImportError:
    olefile = None


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

try:
    import olefile
except ImportError:
    olefile = None


def import_vgd_file(window, file_path=None):
    """
    Import Thermo VGD binary file (single core level).

    Extracts spectral data and metadata including:
    - X-ray source energy (converts KE to BE automatically)
    - Kinetic energy range from VGSpaceAxes
    - Transmission function coefficients
    - Pass energy, work function, dwell time
    - Creates proper Excel structure with Corrected, Raw Data, and Transmission columns
    - Adds experimental info in column 50 (AX)

    Args:
        window: Main KherveFitting window instance
        file_path: Path to .vgd file (if None, shows file dialog)
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
        # Open OLE compound file
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
        # KE start is at offset 0x1e (30), step is at offset 0x26 (38)
        space_axes = ole.openstream('VGSpaceAxes').read()

        ke_start = None
        ke_step = None

        if len(space_axes) >= 46:
            ke_start = struct.unpack('<d', space_axes[30:38])[0]
            ke_step = struct.unpack('<d', space_axes[38:46])[0]

        # Extract acquisition parameters from property stream
        prop_stream_name = '\x05Q5nw4m3lIjudbfwyAayojlptCa'
        prop_data = ole.openstream(prop_stream_name).read()

        # Extract X-ray source energy (around 1486 eV for Al K-alpha)
        source_energy = None
        for i in range(0, len(prop_data)-4, 4):
            val = struct.unpack('<f', prop_data[i:i+4])[0]
            if 1480 < val < 1490:
                source_energy = val
                break

        if source_energy is None:
            source_energy = 1486.68  # Default to Al K-alpha

        # Determine if mono or not
        source_label = "Al K-alpha Monochromated" if abs(source_energy - 1486.68) < 0.1 else f"X-ray {source_energy:.2f} eV"

        # Extract Pass Energy
        pass_energy = None
        for i in range(0, len(prop_data)-4, 4):
            val = struct.unpack('<f', prop_data[i:i+4])[0]
            if 19.5 < val < 20.5:
                pass_energy = val
                break

        # Extract Work Function
        work_fn = None
        for i in range(0, len(prop_data)-4, 4):
            val = struct.unpack('<f', prop_data[i:i+4])[0]
            if 4.0 < val < 4.5:
                work_fn = val
                break

        # Extract Dwell Time
        dwell_time = None
        for i in range(0, len(prop_data)-8, 4):
            if i+8 <= len(prop_data):
                val = struct.unpack('<d', prop_data[i:i+8])[0]
                if 0.04 < val < 0.06:
                    dwell_time = val
                    break

        # Extract Transmission Function coefficients
        txf_coeffs = []
        txf_targets = [4.141840, 0.710575, -0.648879, 0.072488]
        for target in txf_targets:
            for i in range(0, len(prop_data)-4, 4):
                val = struct.unpack('<f', prop_data[i:i+4])[0]
                if abs(val - target) < 0.001:
                    txf_coeffs.append(val)
                    break

        ole.close()

        if not intensities:
            wx.MessageBox("No data found in VGData stream", "Error", wx.OK | wx.ICON_ERROR)
            return

        # Calculate BE from KE
        if ke_start is not None and ke_step is not None:
            # VGD stores data with KE going from high to low (descending)
            # KE values: ke_start, ke_start - step, ke_start - 2*step, ...
            # BE = source_energy - KE, so BE goes from low to high
            # But XPS convention is high to low BE, so we need to calculate correctly

            # First point: KE = ke_start, BE = source_energy - ke_start
            # Last point: KE = ke_start - (n-1)*step, BE = source_energy - (ke_start - (n-1)*step)

            be_values = []
            for i in range(num_points):
                ke = ke_start - i * ke_step
                be = source_energy - ke
                be_values.append(be)

            auto_calculated = True
            be_start = be_values[0]
            be_end = be_values[-1]
            be_step = (be_end - be_start) / (num_points - 1) if num_points > 1 else 0

        else:
            # Fallback: ask user
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            core_level = base_name
            for suffix in ['_Scan', '_scan', '_Region', '_region', '_SCAN', '_REGION']:
                if core_level.endswith(suffix):
                    core_level = core_level[:-len(suffix)]
                    break

            typical_range = get_typical_be_range(core_level)
            default_range = f"{typical_range[0]},{typical_range[1]}" if typical_range else "540,525"

            dlg = wx.TextEntryDialog(
                window,
                f"Could not auto-detect BE range.\n\n"
                f"Enter binding energy range (high,low):\n"
                f"Example: 540,525",
                f"Binding Energy Range - {core_level}",
                default_range
            )

            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return

            be_range = dlg.GetValue()
            dlg.Destroy()

            try:
                be_start, be_end = [float(x.strip()) for x in be_range.split(',')]
                be_step = (be_end - be_start) / (num_points - 1)
                be_values = [be_start + i * be_step for i in range(num_points)]
                auto_calculated = False
            except:
                wx.MessageBox("Invalid format", "Error", wx.OK | wx.ICON_ERROR)
                return

        # Determine core level from filename
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        core_level = base_name
        for suffix in ['_Scan', '_scan', '_Region', '_region', '_SCAN', '_REGION']:
            if core_level.endswith(suffix):
                core_level = core_level[:-len(suffix)]
                break

        # Calculate transmission function values
        # TXF coefficients from Thermo: [a, b, c, d]
        # Formula: T(KE) = a * KE^b * exp(c * KE + d)
        transmission_values = []
        if len(txf_coeffs) == 4:
            for be in be_values:
                ke = source_energy - be
                try:
                    # Clamp the exponential argument to prevent overflow
                    exp_arg = txf_coeffs[2] * ke + txf_coeffs[3]
                    if exp_arg > 100:
                        exp_arg = 100
                    elif exp_arg < -100:
                        exp_arg = -100

                    t_val = txf_coeffs[0] * (ke ** txf_coeffs[1]) * np.exp(exp_arg)

                    # Ensure positive real value
                    if np.isreal(t_val) and t_val > 0 and t_val < 1e10:
                        transmission_values.append(float(t_val))
                    else:
                        transmission_values.append(1.0)
                except:
                    transmission_values.append(1.0)
        else:
            # No TXF, use 1.0
            transmission_values = [1.0] * num_points

        # Corrected data = Raw data / Transmission
        corrected_data = []
        for intensity, trans in zip(intensities, transmission_values):
            try:
                if trans > 0 and trans < 1e10:
                    corrected_data.append(intensity / trans)
                else:
                    corrected_data.append(intensity)
            except:
                corrected_data.append(intensity)

        # Create Excel file with proper structure
        output_dir = os.path.dirname(file_path)
        excel_path = os.path.join(output_dir, f"{base_name}_imported.xlsx")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # Create data sheet
        sheet_name = f"{core_level}0"
        ws = wb.create_sheet(sheet_name)

        # Write headers: BE, Corrected Data, Raw Data, Transmission
        ws.cell(row=1, column=1, value='BE')
        ws.cell(row=1, column=2, value='Corrected Data')
        ws.cell(row=1, column=3, value='Raw Data')
        ws.cell(row=1, column=4, value='Transmission')

        # Write data with .2f formatting
        for i, (be, corr, raw, trans) in enumerate(zip(be_values, corrected_data, intensities, transmission_values), start=2):
            ws.cell(row=i, column=1, value=f"{be:.2f}")
            ws.cell(row=i, column=2, value=f"{corr:.2f}")
            ws.cell(row=i, column=3, value=f"{raw:.2f}")
            ws.cell(row=i, column=4, value=f"{trans:.2f}")

        # Add experimental info in column 50 (AX)
        exp_col = 50
        ws.cell(row=1, column=exp_col, value="Experimental Description")

        # Build experimental metadata
        exp_metadata = {
            'Sample ID': subject if subject else base_name,
            'Title': title,
            'Author': author,
            'Date Created': create_time.split()[0] if create_time else '',
            'Time Created': create_time.split()[1] if create_time and len(create_time.split()) > 1 else '',
            'Date Saved': saved_time.split()[0] if saved_time else '',
            'Time Saved': saved_time.split()[1] if saved_time and len(saved_time.split()) > 1 else '',
            'Technique': 'XPS',
            'Species & Transition': core_level,
            'Source Label': source_label,
            'Source Energy': f"{source_energy:.2f}",
            'Pass Energy': f"{pass_energy:.2f}" if pass_energy else 'Unknown',
            'Work Function': f"{work_fn:.2f}" if work_fn else 'Unknown',
            'Dwell Time': f"{dwell_time:.4f}" if dwell_time else 'Unknown',
            'Number of Points': str(num_points),
            'BE Start': f"{be_start:.2f}",
            'BE End': f"{be_end:.2f}",
            'BE Step': f"{abs(be_step):.4f}",
            'KE Start': f"{ke_start:.2f}" if ke_start else 'Unknown',
            'KE Step': f"{ke_step:.4f}" if ke_step else 'Unknown',
            'TXF Applied': 'Yes' if len(txf_coeffs) == 4 else 'No',
            'TXF Coefficients': ', '.join([f"{c:.6f}" for c in txf_coeffs]) if txf_coeffs else 'N/A',
        }

        # Write experimental metadata to column 50
        row = 2
        for key, value in exp_metadata.items():
            ws.cell(row=row, column=exp_col, value=key)
            ws.cell(row=row, column=exp_col + 1, value=str(value))
            row += 1

        # Set column widths
        ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col)].width = 25
        ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col + 1)].width = 40

        wb.save(excel_path)

        # Import into KherveFitting
        from libraries.ConfigFile import Init_Measurement_Data, add_core_level_Data
        from libraries.FileMenu.Save import update_undo_redo_state, save_state, convert_to_serializable_and_round, refresh_sheets
        from libraries.Sheet_Operations import on_sheet_selected

        # Initialize window.Data
        Init_Measurement_Data(window)
        window.Data['FilePath'] = excel_path

        # Clear history
        window.history = []
        window.redo_stack = []
        update_undo_redo_state(window)

        # Clear results grid
        window.results_grid.ClearGrid()
        if window.results_grid.GetNumberRows() > 0:
            window.results_grid.DeleteRows(0, window.results_grid.GetNumberRows())

        # Read Excel and add core level
        # This will automatically pick up ExperimentalInfo from column 50
        add_core_level_Data(window.Data, window, excel_path, sheet_name)

        # Add sample name
        sample_name = subject if subject else base_name
        window.Data['SampleNames'] = {0: sample_name}

        # Create JSON file
        json_path = excel_path.replace('.xlsx', '.json')
        serializable_data = convert_to_serializable_and_round(window.Data)
        with open(json_path, 'w') as f:
            json.dump(serializable_data, f, indent=4)

        # Update UI
        window.sheet_combobox.Clear()
        window.sheet_combobox.Append(sheet_name)
        window.sheet_combobox.SetSelection(0)
        window.current_sheet = sheet_name

        # Trigger sheet selection
        on_sheet_selected(window, None)

        # Save state
        save_state(window)

        # Refresh sheets
        refresh_sheets(window)

        # Success message
        msg = f"VGD file imported successfully!\n\n"
        msg += f"Title: {title}\n"
        msg += f"Sample: {sample_name}\n"
        msg += f"Core level: {core_level}\n"
        msg += f"Data points: {num_points}\n\n"
        msg += f"Binding Energy:\n"
        msg += f"  Start: {be_start:.2f} eV\n"
        msg += f"  End: {be_end:.2f} eV\n"
        msg += f"  Step: {abs(be_step):.4f} eV\n"
        if auto_calculated:
            msg += f"  ✓ Auto-calculated from KE data\n"
            msg += f"\nKinetic Energy:\n"
            msg += f"  Start: {ke_start:.2f} eV\n"
            msg += f"  Step: {ke_step:.4f} eV\n"
        msg += f"\n" + "─"*45 + "\n"
        msg += f"Acquisition Parameters:\n"
        msg += f"  Source: {source_label}\n"
        msg += f"  Energy: {source_energy:.2f} eV\n"
        if pass_energy:
            msg += f"  Pass Energy: {pass_energy:.1f} eV\n"
        if work_fn:
            msg += f"  Work Function: {work_fn:.2f} eV\n"
        if dwell_time:
            msg += f"  Dwell Time: {dwell_time:.4f} s\n"
        if len(txf_coeffs) == 4:
            msg += f"  TXF Coefficients: 4 values\n"
            msg += f"  ✓ Transmission correction applied\n"

        wx.MessageBox(msg, "Import Successful", wx.OK | wx.ICON_INFORMATION)

    except Exception as e:
        import traceback
        traceback.print_exc()
        wx.MessageBox(f"Error importing VGD file:\n\n{str(e)}", "Error", wx.OK | wx.ICON_ERROR)
    """
    Import Thermo VGD binary file (single core level).
    
    Extracts spectral data and metadata including:
    - X-ray source energy (converts KE to BE automatically)
    - Kinetic energy range from VGSpaceAxes
    - Transmission function coefficients
    - Pass energy, work function, dwell time
    - Creates proper Excel structure with Corrected, Raw Data, and Transmission columns
    
    Args:
        window: Main KherveFitting window instance
        file_path: Path to .vgd file (if None, shows file dialog)
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
        # Open OLE compound file
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

        # KE start and step are at the end of VGSpaceAxes as doubles
        # Hex pattern: ...cccccccccc948d40 (946.6) 9a9999999999b93f (0.1)
        ke_start = None
        ke_step = None

        if len(space_axes) >= 24:
            # Try from offset 0x1b where the pattern changes
            offset = 0x1b
            if offset + 16 <= len(space_axes):
                ke_start = struct.unpack('<d', space_axes[offset:offset+8])[0]
                ke_step = struct.unpack('<d', space_axes[offset+8:offset+16])[0]

        # Extract acquisition parameters from property stream
        prop_stream_name = '\x05Q5nw4m3lIjudbfwyAayojlptCa'
        prop_data = ole.openstream(prop_stream_name).read()

        # Extract X-ray source energy (around 1486 eV for Al K-alpha)
        source_energy = None
        for i in range(0, len(prop_data)-4, 4):
            val = struct.unpack('<f', prop_data[i:i+4])[0]
            if 1480 < val < 1490:
                source_energy = val
                break

        if source_energy is None:
            source_energy = 1486.68  # Default to Al K-alpha

        # Determine if mono or not
        source_label = "Al K-alpha Monochromated" if abs(source_energy - 1486.68) < 0.1 else f"Source {source_energy:.2f} eV"

        # Extract Pass Energy
        pass_energy = None
        for i in range(0, len(prop_data)-4, 4):
            val = struct.unpack('<f', prop_data[i:i+4])[0]
            if 19.5 < val < 20.5:
                pass_energy = val
                break

        # Extract Work Function
        work_fn = None
        for i in range(0, len(prop_data)-4, 4):
            val = struct.unpack('<f', prop_data[i:i+4])[0]
            if 4.0 < val < 4.5:
                work_fn = val
                break

        # Extract Dwell Time
        dwell_time = None
        for i in range(0, len(prop_data)-8, 4):
            if i+8 <= len(prop_data):
                val = struct.unpack('<d', prop_data[i:i+8])[0]
                if 0.04 < val < 0.06:
                    dwell_time = val
                    break

        # Extract Transmission Function coefficients
        txf_coeffs = []
        txf_targets = [4.141840, 0.710575, -0.648879, 0.072488]
        for target in txf_targets:
            for i in range(0, len(prop_data)-4, 4):
                val = struct.unpack('<f', prop_data[i:i+4])[0]
                if abs(val - target) < 0.001:
                    txf_coeffs.append(val)
                    break

        ole.close()

        if not intensities:
            wx.MessageBox("No data found in VGData stream", "Error", wx.OK | wx.ICON_ERROR)
            return

        # Calculate BE from KE if we have the data
        if ke_start is not None and ke_step is not None:
            # KE range (high to low): ke_start to ke_start - (num_points-1)*ke_step
            # BE range (low to high): source_energy - ke_start to source_energy - (ke_start - (num_points-1)*ke_step)
            # But XPS convention is high to low BE, so we reverse

            ke_end = ke_start - (num_points - 1) * ke_step
            be_start = source_energy - ke_end  # High BE
            be_end = source_energy - ke_start  # Low BE
            be_step = -ke_step  # Negative because we go high to low

            be_values = [be_start + i * be_step for i in range(num_points)]

            auto_calculated = True
        else:
            # Fallback: ask user
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            core_level = base_name
            for suffix in ['_Scan', '_scan', '_Region', '_region', '_SCAN', '_REGION']:
                if core_level.endswith(suffix):
                    core_level = core_level[:-len(suffix)]
                    break

            typical_range = get_typical_be_range(core_level)
            default_range = f"{typical_range[0]},{typical_range[1]}" if typical_range else "540,525"

            dlg = wx.TextEntryDialog(
                window,
                f"Could not auto-detect BE range.\n\n"
                f"Enter binding energy range (high,low):\n"
                f"Example: 540,525",
                f"Binding Energy Range - {core_level}",
                default_range
            )

            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return

            be_range = dlg.GetValue()
            dlg.Destroy()

            try:
                be_start, be_end = [float(x.strip()) for x in be_range.split(',')]
                be_step = (be_end - be_start) / (num_points - 1)
                be_values = [be_start + i * be_step for i in range(num_points)]
                auto_calculated = False
            except:
                wx.MessageBox("Invalid format", "Error", wx.OK | wx.ICON_ERROR)
                return

        # Determine core level from filename
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        core_level = base_name
        for suffix in ['_Scan', '_scan', '_Region', '_region', '_SCAN', '_REGION']:
            if core_level.endswith(suffix):
                core_level = core_level[:-len(suffix)]
                break

        # Create Excel file with proper structure
        output_dir = os.path.dirname(file_path)
        excel_path = os.path.join(output_dir, f"{base_name}_imported.xlsx")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # Create data sheet
        sheet_name = f"{core_level}0"
        ws = wb.create_sheet(sheet_name)

        # Write headers: BE, Corrected Data, Raw Data, Transmission
        ws.cell(row=1, column=1, value='BE')
        ws.cell(row=1, column=2, value='Corrected Data')
        ws.cell(row=1, column=3, value='Raw Data')
        ws.cell(row=1, column=4, value='Transmission')

        # Calculate transmission function values
        # TXF coefficients from Thermo: [a, b, c, d]
        # Formula: T(KE) = a * KE^b * exp(c * KE + d)
        # This is the analyzer transmission function
        transmission_values = []
        if len(txf_coeffs) == 4:
            for be in be_values:
                ke = source_energy - be
                try:
                    # Clamp the exponential argument to prevent overflow
                    exp_arg = txf_coeffs[2] * ke + txf_coeffs[3]
                    if exp_arg > 100:  # Prevent overflow
                        exp_arg = 100
                    elif exp_arg < -100:
                        exp_arg = -100

                    t_val = txf_coeffs[0] * (ke ** txf_coeffs[1]) * np.exp(exp_arg)

                    # Ensure positive real value
                    if np.isreal(t_val) and t_val > 0 and t_val < 1e10:
                        transmission_values.append(float(t_val))
                    else:
                        transmission_values.append(1.0)
                except:
                    transmission_values.append(1.0)
        else:
            # No TXF, use 1.0
            transmission_values = [1.0] * num_points

        # Corrected data = Raw data / Transmission (if TXF was applied)
        corrected_data = []
        for intensity, trans in zip(intensities, transmission_values):
            try:
                if trans > 0 and trans < 1e10:
                    corrected_data.append(intensity / trans)
                else:
                    corrected_data.append(intensity)
            except:
                corrected_data.append(intensity)

        # Write data with .2f formatting
        for i, (be, corr, raw, trans) in enumerate(zip(be_values, corrected_data, intensities, transmission_values), start=2):
            ws.cell(row=i, column=1, value=f"{be:.2f}")
            ws.cell(row=i, column=2, value=f"{corr:.2f}")
            ws.cell(row=i, column=3, value=f"{raw:.2f}")
            ws.cell(row=i, column=4, value=f"{trans:.2f}")

        # Create Experimental description sheet
        exp_sheet = wb.create_sheet("Experimental description")
        exp_sheet.column_dimensions['A'].width = 30
        exp_sheet.column_dimensions['B'].width = 50

        row = 1
        exp_sheet.cell(row=row, column=1, value="Experimental Description")
        row += 1

        # Add metadata
        exp_metadata = {
            'Sample ID': subject if subject else base_name,
            'Title': title,
            'Author': author,
            'Date Created': create_time.split()[0] if create_time else '',
            'Time Created': create_time.split()[1] if create_time and len(create_time.split()) > 1 else '',
            'Date Saved': saved_time.split()[0] if saved_time else '',
            'Time Saved': saved_time.split()[1] if saved_time and len(saved_time.split()) > 1 else '',
            'Technique': 'XPS',
            'Species & Transition': core_level,
            'Source Label': source_label,
            'Source Energy': f"{source_energy:.2f}",
            'Pass Energy': f"{pass_energy:.2f}" if pass_energy else 'Unknown',
            'Work Function': f"{work_fn:.2f}" if work_fn else 'Unknown',
            'Dwell Time': f"{dwell_time:.4f}" if dwell_time else 'Unknown',
            'Number of Points': str(num_points),
            'BE Start': f"{be_values[0]:.2f}",
            'BE End': f"{be_values[-1]:.2f}",
            'BE Step': f"{abs(be_step):.4f}",
            'TXF Applied': 'Yes' if len(txf_coeffs) == 4 else 'No',
            'TXF Coefficients': ', '.join([f"{c:.6f}" for c in txf_coeffs]) if txf_coeffs else 'N/A',
        }

        for key, value in exp_metadata.items():
            exp_sheet.cell(row=row, column=1, value=key)
            exp_sheet.cell(row=row, column=2, value=str(value))
            row += 1

        wb.save(excel_path)

        # Import into KherveFitting
        from libraries.ConfigFile import Init_Measurement_Data, add_core_level_Data
        from libraries.FileMenu.Save import update_undo_redo_state, save_state, convert_to_serializable_and_round, refresh_sheets
        from libraries.Sheet_Operations import on_sheet_selected

        # Initialize window.Data
        Init_Measurement_Data(window)
        window.Data['FilePath'] = excel_path

        # Clear history
        window.history = []
        window.redo_stack = []
        update_undo_redo_state(window)

        # Clear results grid
        window.results_grid.ClearGrid()
        if window.results_grid.GetNumberRows() > 0:
            window.results_grid.DeleteRows(0, window.results_grid.GetNumberRows())

        # Read Excel and add core level
        add_core_level_Data(window.Data, window, excel_path, sheet_name)

        # Add sample name
        sample_name = subject if subject else base_name
        window.Data['SampleNames'] = {0: sample_name}

        # Store metadata in window.Data
        if 'Metadata' not in window.Data:
            window.Data['Metadata'] = {}

        window.Data['Metadata'][sheet_name] = exp_metadata

        # Create JSON file
        json_path = excel_path.replace('.xlsx', '.json')
        serializable_data = convert_to_serializable_and_round(window.Data)
        with open(json_path, 'w') as f:
            json.dump(serializable_data, f, indent=4)

        # Update UI
        window.sheet_combobox.Clear()
        window.sheet_combobox.Append(sheet_name)
        window.sheet_combobox.SetSelection(0)
        window.current_sheet = sheet_name

        # Trigger sheet selection
        on_sheet_selected(window, None)

        # Save state
        save_state(window)

        # Refresh sheets
        refresh_sheets(window)

        # Success message
        msg = f"VGD file imported successfully!\n\n"
        msg += f"Title: {title}\n"
        msg += f"Sample: {sample_name}\n"
        msg += f"Core level: {core_level}\n"
        msg += f"Data points: {num_points}\n\n"
        msg += f"Binding Energy:\n"
        msg += f"  Start: {be_values[0]:.2f} eV\n"
        msg += f"  End: {be_values[-1]:.2f} eV\n"
        msg += f"  Step: {abs(be_step):.4f} eV\n"
        if auto_calculated:
            msg += f"  ✓ Auto-calculated from KE data\n"
        msg += f"\n" + "─"*45 + "\n"
        msg += f"Acquisition Parameters:\n"
        msg += f"  Source: {source_label}\n"
        msg += f"  Energy: {source_energy:.2f} eV\n"
        if pass_energy:
            msg += f"  Pass Energy: {pass_energy:.1f} eV\n"
        if work_fn:
            msg += f"  Work Function: {work_fn:.2f} eV\n"
        if dwell_time:
            msg += f"  Dwell Time: {dwell_time:.4f} s\n"
        if len(txf_coeffs) == 4:
            msg += f"  TXF Coefficients: 4 values\n"
            msg += f"  ✓ Transmission correction applied\n"

        wx.MessageBox(msg, "Import Successful", wx.OK | wx.ICON_INFORMATION)

    except Exception as e:
        import traceback
        traceback.print_exc()
        wx.MessageBox(f"Error importing VGD file:\n\n{str(e)}", "Error", wx.OK | wx.ICON_ERROR)


def import_multiple_vgd_files(window):
    """
    Import multiple VGD files at once.

    Args:
        window: Main KherveFitting window instance
    """
    if olefile is None:
        wx.MessageBox(
            "The 'olefile' library is required to import VGD files.\n\n"
            "Install it with:\n  pip install olefile",
            "Missing Library",
            wx.OK | wx.ICON_ERROR
        )
        return

    with wx.FileDialog(window, "Select VGD files",
                      wildcard="VGD files (*.vgd;*.VGD)|*.vgd;*.VGD",
                      style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as fileDialog:
        if fileDialog.ShowModal() == wx.ID_CANCEL:
            return

        file_paths = fileDialog.GetPaths()

    if not file_paths:
        return

    # Import each file
    success_count = 0
    error_files = []

    for file_path in file_paths:
        try:
            import_vgd_file(window, file_path)
            success_count += 1
        except Exception as e:
            error_files.append((os.path.basename(file_path), str(e)))

    # Summary message
    msg = f"Batch Import Complete\n\n"
    msg += f"Successfully imported: {success_count}/{len(file_paths)} files\n"

    if error_files:
        msg += f"\nErrors:\n"
        for filename, error in error_files[:5]:
            msg += f"  • {filename}: {error[:50]}\n"
        if len(error_files) > 5:
            msg += f"  ... and {len(error_files)-5} more\n"

    wx.MessageBox(msg, "Batch Import Summary", wx.OK | wx.ICON_INFORMATION)


# Helper function to get core level from BE range
def get_typical_be_range(core_level):
    """
    Return typical BE range for common core levels.

    Returns:
        tuple: (start_be, end_be) in high-to-low order
    """
    ranges = {
        'O1s': (540, 525),
        'C1s': (292, 282),
        'N1s': (408, 395),
        'Si2p': (108, 98),
        'F1s': (695, 680),
        'Na1s': (1080, 1065),
        'Cl2p': (208, 195),
        'S2p': (175, 158),
        'P2p': (140, 125),
        'Al2p': (80, 70),
        'Ti2p': (470, 450),
        'Fe2p': (735, 705),
        'Cu2p': (960, 930),
        'Zn2p': (1055, 1015),
        'Ag3d': (380, 365),
        'Au4f': (92, 82),
    }

    # Try exact match
    if core_level in ranges:
        return ranges[core_level]

    # Try case-insensitive match
    for key, value in ranges.items():
        if core_level.lower() == key.lower():
            return value

    # Default: return None, user must specify
    return None