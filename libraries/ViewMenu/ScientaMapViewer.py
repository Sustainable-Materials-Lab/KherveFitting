"""
Scienta Map Viewer Window for KherveFitting

Opens when clicking on a ~Map sheet in Sample Manager.
Displays a single map with tools for:
- Dropping sweeps
- Binning into N groups
- Summing all sweeps
Creates new core level sheets in the current working file.
"""

import os
import re
import numpy as np
import wx
import json
import openpyxl
import matplotlib
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib.figure import Figure


class ScientaMapViewerWindow(wx.Frame):
    """
    Window to view and manipulate a single Scienta map from window.Data.
    """

    def __init__(self, parent, map_sheet_name):
        """
        Initialize the map viewer window.

        Args:
            parent: Parent window (main KherveFitting window)
            map_sheet_name: Name of the map sheet (e.g., 'Ce3d~Map')
        """
        super().__init__(parent, title=f"Map Viewer - {map_sheet_name}",
                        size=(700, 600), style=wx.DEFAULT_FRAME_STYLE)

        self.parent = parent
        self.map_sheet_name = map_sheet_name

        # Extract map data from window.Data
        if map_sheet_name not in parent.Data['Core levels']:
            wx.MessageBox(f"Map sheet '{map_sheet_name}' not found in data.",
                         "Error", wx.OK | wx.ICON_ERROR)
            self.Close()
            return

        map_data = parent.Data['Core levels'][map_sheet_name]

        # Get BE values
        self.be_values = np.array(map_data.get('B.E.', []))

        # Build 2D data array from Y columns
        self.num_sweeps = map_data.get('_num_sweeps', 0)
        if self.num_sweeps == 0:
            # Count Y columns
            self.num_sweeps = sum(1 for key in map_data.keys() if key.startswith('Y') and key[1:].isdigit())

        if self.num_sweeps == 0 or len(self.be_values) == 0:
            wx.MessageBox(f"Invalid map data in '{map_sheet_name}'.",
                         "Error", wx.OK | wx.ICON_ERROR)
            self.Close()
            return

        # Build data_2d array (num_sweeps x num_be_points)
        self.data_2d = np.zeros((self.num_sweeps, len(self.be_values)))
        for i in range(self.num_sweeps):
            col_name = f'Y{i + 1}'
            if col_name in map_data:
                self.data_2d[i, :] = np.array(map_data[col_name])

        self.metadata = map_data.get('ExperimentalInfo', {})
        self.dropped_sweeps = []
        self.current_sweep_index = 0

        # Extract base name (e.g., 'Ce3d' from 'zzMap~Ce3d' or 'Ce3d~Map')
        if map_sheet_name.startswith('zzMap~'):
            self.base_name = map_sheet_name[6:]  # Remove 'zzMap~'
        elif '~Map' in map_sheet_name:
            self.base_name = map_sheet_name.replace('~Map', '')
        else:
            self.base_name = map_sheet_name

        self.init_ui()
        self.update_heatmap()

        self.Centre()
        self.Show()

    def init_ui(self):
        """Initialize the user interface."""
        main_panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Title label
        title_label = wx.StaticText(main_panel, label=f"Map: {self.map_sheet_name}")
        title_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        main_sizer.Add(title_label, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        # Control panel
        control_panel = wx.Panel(main_panel)
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Sweep selector
        sweep_label = wx.StaticText(control_panel, label="Sweep:")
        control_sizer.Add(sweep_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.sweep_spin = wx.SpinCtrl(control_panel, min=1, max=self.num_sweeps, initial=1, size=(70, -1))
        self.sweep_spin.Bind(wx.EVT_SPINCTRL, self.on_sweep_changed)
        control_sizer.Add(self.sweep_spin, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        sweep_info = wx.StaticText(control_panel, label=f"/ {self.num_sweeps}")
        control_sizer.Add(sweep_info, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 15)

        # Drop button
        self.drop_btn = wx.Button(control_panel, label="Drop Sweep", size=(80, -1))
        self.drop_btn.SetBackgroundColour(wx.Colour(255, 200, 200))
        self.drop_btn.Bind(wx.EVT_BUTTON, self.on_drop_sweep)
        control_sizer.Add(self.drop_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        # Undo button
        self.undo_btn = wx.Button(control_panel, label="Undo", size=(60, -1))
        self.undo_btn.Bind(wx.EVT_BUTTON, self.on_undo_drop)
        self.undo_btn.Enable(False)
        control_sizer.Add(self.undo_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        control_sizer.AddStretchSpacer()

        # Status text
        self.status_text = wx.StaticText(control_panel, label="")
        control_sizer.Add(self.status_text, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        control_panel.SetSizer(control_sizer)
        main_sizer.Add(control_panel, 0, wx.EXPAND | wx.ALL, 5)

        # Create figure for heatmap (larger for single map)
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(main_panel, -1, self.figure)
        main_sizer.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 5)

        # Toolbar
        toolbar = NavigationToolbar(self.canvas)
        main_sizer.Add(toolbar, 0, wx.EXPAND)

        # Action panel
        action_panel = wx.Panel(main_panel)
        action_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Binning controls
        bin_label = wx.StaticText(action_panel, label="Number of Bins:")
        action_sizer.Add(bin_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.bin_spin = wx.SpinCtrl(action_panel, min=1, max=self.num_sweeps, initial=1, size=(70, -1))
        action_sizer.Add(self.bin_spin, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.bin_btn = wx.Button(action_panel, label="Create Binned Spectra", size=(140, -1))
        self.bin_btn.SetBackgroundColour(wx.Colour(200, 200, 255))
        self.bin_btn.Bind(wx.EVT_BUTTON, self.on_bin_create)
        action_sizer.Add(self.bin_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        action_sizer.AddStretchSpacer()

        # Sum button
        self.sum_btn = wx.Button(action_panel, label="Create Summed Spectrum", size=(150, -1))
        self.sum_btn.SetBackgroundColour(wx.Colour(200, 255, 200))
        self.sum_btn.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.sum_btn.Bind(wx.EVT_BUTTON, self.on_sum_create)
        action_sizer.Add(self.sum_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 10)

        action_panel.SetSizer(action_sizer)
        main_sizer.Add(action_panel, 0, wx.EXPAND | wx.ALL, 5)

        main_panel.SetSizer(main_sizer)

        self.update_status()

    def update_heatmap(self):
        """Update the heatmap display."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Get data - mask dropped sweeps with NaN
        data = self.data_2d.copy()
        for dropped_idx in self.dropped_sweeps:
            data[dropped_idx, :] = np.nan

        be_min, be_max = self.be_values.min(), self.be_values.max()

        # Plot heatmap with Greens colormap
        im = ax.imshow(data, aspect='auto', origin='lower',
                      extent=[be_min, be_max, 0.5, self.num_sweeps + 0.5],
                      cmap='Greens')

        # Add colorbar
        cbar = self.figure.colorbar(im, ax=ax)
        cbar.set_label('Intensity', fontsize=10)

        # Add horizontal line at current sweep
        ax.axhline(y=self.current_sweep_index + 1, color='red',
                  linewidth=2, linestyle='--', label='Current sweep')

        ax.set_xlabel('Binding Energy (eV)', fontsize=11)
        ax.set_ylabel('Sweep Number', fontsize=11)
        ax.set_title(f'{self.base_name} - {self.num_sweeps - len(self.dropped_sweeps)} active sweeps', fontsize=12)
        ax.tick_params(labelsize=9)
        ax.invert_xaxis()

        self.figure.tight_layout()
        self.canvas.draw()

    def update_status(self):
        """Update the status text."""
        if self.dropped_sweeps:
            self.status_text.SetLabel(f"Dropped: {len(self.dropped_sweeps)} sweep(s)")
            self.undo_btn.Enable(True)
        else:
            self.status_text.SetLabel("")
            self.undo_btn.Enable(False)

    def on_sweep_changed(self, event):
        """Handle sweep spin control change."""
        self.current_sweep_index = self.sweep_spin.GetValue() - 1
        self.update_heatmap()

    def on_drop_sweep(self, event):
        """Drop the current sweep."""
        sweep_idx = self.current_sweep_index

        if sweep_idx not in self.dropped_sweeps and sweep_idx < self.num_sweeps:
            self.dropped_sweeps.append(sweep_idx)

        self.update_heatmap()
        self.update_status()

        # Move to next sweep if possible
        if self.current_sweep_index < self.num_sweeps - 1:
            self.current_sweep_index += 1
            self.sweep_spin.SetValue(self.current_sweep_index + 1)

    def on_undo_drop(self, event):
        """Undo the last dropped sweep."""
        if self.dropped_sweeps:
            last_dropped = self.dropped_sweeps.pop()
            self.current_sweep_index = last_dropped
            self.sweep_spin.SetValue(self.current_sweep_index + 1)
            self.update_heatmap()
            self.update_status()

    def on_bin_create(self, event):
        """Create binned spectra from the map."""
        num_bins = self.bin_spin.GetValue()

        # Get valid sweep indices
        valid_indices = [i for i in range(self.num_sweeps) if i not in self.dropped_sweeps]

        if not valid_indices:
            wx.MessageBox("All sweeps have been dropped!", "Error", wx.OK | wx.ICON_ERROR)
            return

        n_valid = len(valid_indices)
        bin_size = n_valid // num_bins
        remainder = n_valid % num_bins

        if bin_size == 0:
            wx.MessageBox(f"Not enough sweeps ({n_valid}) for {num_bins} bins.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return

        # Create binned spectra
        created_sheets = []
        start = 0

        for b in range(num_bins):
            size = bin_size + (1 if b < remainder else 0)
            if size == 0:
                continue
            end = start + size
            bin_indices = valid_indices[start:end]

            # Sum intensities in this bin
            bin_data = self.data_2d[bin_indices, :]
            summed = np.sum(bin_data, axis=0)

            # Create new sheet name
            if num_bins > 1:
                new_sheet_name = f"{self.base_name}{b + 1}"
            else:
                new_sheet_name = self.base_name

            # Ensure unique name
            existing_sheets = list(self.parent.Data['Core levels'].keys())
            base_new_name = new_sheet_name
            counter = 1
            while new_sheet_name in existing_sheets:
                new_sheet_name = f"{base_new_name}{counter}"
                counter += 1

            # Add to window.Data
            self.add_spectrum_to_data(new_sheet_name, summed, bin_indices)
            created_sheets.append(new_sheet_name)

            start = end

        # Save and refresh
        self.save_and_refresh(created_sheets)

        wx.MessageBox(f"Created {len(created_sheets)} binned spectrum sheet(s):\n" +
                     "\n".join(created_sheets), "Success", wx.OK | wx.ICON_INFORMATION)

    def on_sum_create(self, event):
        """Create a single summed spectrum from all valid sweeps."""
        # Get valid sweep indices
        valid_indices = [i for i in range(self.num_sweeps) if i not in self.dropped_sweeps]

        if not valid_indices:
            wx.MessageBox("All sweeps have been dropped!", "Error", wx.OK | wx.ICON_ERROR)
            return

        # Sum all valid sweeps
        valid_data = self.data_2d[valid_indices, :]
        summed = np.sum(valid_data, axis=0)

        # Create new sheet name
        new_sheet_name = self.base_name
        existing_sheets = list(self.parent.Data['Core levels'].keys())
        base_new_name = new_sheet_name
        counter = 1
        while new_sheet_name in existing_sheets:
            new_sheet_name = f"{base_new_name}{counter}"
            counter += 1

        # Add to window.Data
        self.add_spectrum_to_data(new_sheet_name, summed, valid_indices)

        # Save and refresh
        self.save_and_refresh([new_sheet_name])

        wx.MessageBox(f"Created summed spectrum sheet:\n{new_sheet_name}\n"
                     f"({len(valid_indices)} sweeps summed)",
                     "Success", wx.OK | wx.ICON_INFORMATION)

    def add_spectrum_to_data(self, sheet_name, intensities, sweep_indices):
        """Add a new spectrum to window.Data and Excel file."""
        # Create core level data structure
        core_level_data = {
            'Name': sheet_name,
            'B.E.': [round(float(be), 2) for be in self.be_values],
            'Raw Data': [round(float(val), 2) for val in intensities],
            'Corrected Data': [round(float(val), 2) for val in intensities],
            'Transmission': [1.0] * len(self.be_values),
            'Background': {
                'Bkg Type': '',
                'Bkg Low': round(float(min(self.be_values)), 2),
                'Bkg High': round(float(max(self.be_values)), 2),
                'Bkg Offset Low': 0,
                'Bkg Offset High': 0,
                'Bkg Y': [round(float(val), 2) for val in intensities]
            }
        }

        # Add experimental info
        exp_info = dict(self.metadata) if self.metadata else {}
        exp_info['Source Map'] = self.map_sheet_name
        exp_info['Sweeps Used'] = ', '.join(map(str, [i + 1 for i in sweep_indices]))
        exp_info['Number of Sweeps Summed'] = str(len(sweep_indices))
        exp_info['Species & Transition'] = sheet_name
        core_level_data['ExperimentalInfo'] = exp_info

        # Add to window.Data
        self.parent.Data['Core levels'][sheet_name] = core_level_data
        self.parent.Data['Number of Core levels'] = len(self.parent.Data['Core levels'])

        # Also add to Excel file
        self.add_sheet_to_excel(sheet_name, core_level_data)

    def add_sheet_to_excel(self, sheet_name, core_level_data):
        """Add a new sheet to the Excel file."""
        excel_path = self.parent.Data.get('FilePath', '')
        if not excel_path or not os.path.exists(excel_path):
            return

        try:
            wb = openpyxl.load_workbook(excel_path)

            # Create new sheet
            ws = wb.create_sheet(sheet_name)

            # Write headers
            ws.cell(row=1, column=1, value='BE')
            ws.cell(row=1, column=2, value='Raw Data')

            # Write data
            be_values = core_level_data['B.E.']
            raw_data = core_level_data['Raw Data']

            for i, (be, intensity) in enumerate(zip(be_values, raw_data), start=2):
                ws.cell(row=i, column=1, value=be)
                ws.cell(row=i, column=2, value=intensity)

            # Add experimental info
            exp_col = 50
            ws.cell(row=1, column=exp_col, value="Experimental Description")

            exp_info = core_level_data.get('ExperimentalInfo', {})
            row = 2
            for key, value in exp_info.items():
                ws.cell(row=row, column=exp_col, value=key)
                ws.cell(row=row, column=exp_col + 1, value=str(value))
                row += 1

            ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col)].width = 25
            ws.column_dimensions[openpyxl.utils.get_column_letter(exp_col + 1)].width = 40

            wb.save(excel_path)

        except Exception as e:
            print(f"Error adding sheet to Excel: {e}")

    def save_and_refresh(self, new_sheet_names):
        """Save data and refresh the UI."""
        from libraries.FileMenu.Save import save_state, convert_to_serializable_and_round
        from libraries.Sheet_Operations import on_sheet_selected

        # Save JSON
        excel_path = self.parent.Data.get('FilePath', '')
        if excel_path:
            json_path = os.path.splitext(excel_path)[0] + '.json'
            try:
                serializable_data = convert_to_serializable_and_round(self.parent.Data)
                with open(json_path, 'w') as f:
                    json.dump(serializable_data, f, indent=4)
            except Exception as e:
                print(f"Error saving JSON: {e}")

        # Update sheet combobox
        for sheet_name in new_sheet_names:
            if sheet_name not in [self.parent.sheet_combobox.GetString(i)
                                  for i in range(self.parent.sheet_combobox.GetCount())]:
                self.parent.sheet_combobox.Append(sheet_name)

        # Select first new sheet
        if new_sheet_names:
            self.parent.sheet_combobox.SetStringSelection(new_sheet_names[0])
            self.parent.current_sheet = new_sheet_names[0]
            on_sheet_selected(self.parent, None)

        save_state(self.parent)

        # Refresh Sample Manager if open
        if hasattr(self.parent, 'file_manager') and self.parent.file_manager is not None:
            try:
                self.parent.file_manager.populate_grid()
            except:
                pass


def open_scienta_map_viewer(parent, map_sheet_name):
    """
    Open the Scienta Map Viewer window for a ~Map sheet.

    Args:
        parent: Main KherveFitting window
        map_sheet_name: Name of the map sheet to view

    Returns:
        ScientaMapViewerWindow instance or None if failed
    """
    try:
        viewer = ScientaMapViewerWindow(parent, map_sheet_name)
        return viewer
    except Exception as e:
        import traceback
        traceback.print_exc()
        wx.MessageBox(f"Error opening map viewer:\n{str(e)}",
                     "Error", wx.OK | wx.ICON_ERROR)
        return None