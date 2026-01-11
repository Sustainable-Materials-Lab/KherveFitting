"""
Tougaard Quantitative XPS Analysis Window

Based on: "Practical guide to the use of backgrounds in quantitative XPS"
by Sven Tougaard, J. Vac. Sci. Technol. A 39, 011201 (2021)
"""

import wx
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from scipy.optimize import minimize_scalar
from scipy.integrate import trapezoid


class TougaardAnalysisWindow(wx.Frame):
    """Window for Tougaard-based quantitative XPS depth analysis."""

    D0_HOMOGENEOUS = 23.0
    B0_HOMOGENEOUS = 2866.0
    C_UNIVERSAL = 1643.0

    CROSS_SECTIONS = {
        'Universal (metals/oxides)': {'C': 1643.0, 'D': 1.0},
        'SiO2': {'C': 542.0, 'D': 275.0},
        'Polymers': {'C': 551.0, 'D': 436.0},
        'Si': {'C': 542.0, 'D': 275.0},
        'Al': {'C': 542.0, 'D': 275.0},
    }

    def __init__(self, parent):
        # if 'wxMac' in wx.PlatformInfo:
        #     window_size = (950, 620)
        # else:
        #     window_size = (1000, 640)
        # Platform-specific window sizing
        if 'wxMac' in wx.PlatformInfo:
            window_size = (800, 540)  # Smaller for macOS
        elif 'wxGTK' in wx.PlatformInfo:  # Linux
            window_size = (920, 660)
        else:  # Windows
            window_size = (920, 660)

        super().__init__(parent, title="Tougaard Quantitative XPS Analysis",
                         size=window_size, style=wx.DEFAULT_FRAME_STYLE)

        self.parent = parent
        self.current_sheet = None
        self.x_data = None
        self.y_data = None
        self.background = None
        self.fitted_B = None
        self.peak_area = None
        self.B_increase = None
        self.dragging_line = None

        self.InitUI()
        self.Centre()
        self.populate_core_levels()

        if self.core_level_combo.GetCount() > 0:
            self.on_core_level_change(None)

        try:
            from libraries.ConfigFile import set_consistent_fonts
            set_consistent_fonts(self)
        except ImportError:
            pass

    def InitUI(self):
        panel = wx.Panel(self, style=wx.BORDER_RAISED)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        left_panel = wx.Panel(panel)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        # Core Level Selection
        cl_box = wx.StaticBox(left_panel, label="Core Level")
        cl_sizer = wx.StaticBoxSizer(cl_box, wx.VERTICAL)
        self.core_level_combo = wx.ComboBox(cl_box, style=wx.CB_READONLY)
        self.core_level_combo.Bind(wx.EVT_COMBOBOX, self.on_core_level_change)
        cl_sizer.Add(self.core_level_combo, 0, wx.EXPAND | wx.ALL, 0)
        left_sizer.Add(cl_sizer, 0, wx.EXPAND | wx.ALL, 0)

        # Material Parameters
        mat_box = wx.StaticBox(left_panel, label="Material Parameters")
        mat_sizer = wx.StaticBoxSizer(mat_box, wx.VERTICAL)

        cs_row = wx.BoxSizer(wx.HORIZONTAL)
        cs_row.Add(wx.StaticText(mat_box, label="Material:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.cross_section_combo = wx.ComboBox(mat_box, style=wx.CB_READONLY, choices=list(self.CROSS_SECTIONS.keys()))
        self.cross_section_combo.SetValue('Universal (metals/oxides)')
        self.cross_section_combo.Bind(wx.EVT_COMBOBOX, self.on_cross_section_change)
        self.cross_section_combo.SetToolTip("Material type determines the C parameter\nfor the Tougaard cross-section function")
        cs_row.Add(self.cross_section_combo, 1, wx.EXPAND)
        mat_sizer.Add(cs_row, 0, wx.EXPAND | wx.ALL, 4)

        imfp_row = wx.BoxSizer(wx.HORIZONTAL)
        imfp_row.Add(wx.StaticText(mat_box, label="IMFP λ (nm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.imfp_ctrl = wx.SpinCtrlDouble(mat_box, min=0.1, max=10.0, initial=1.5, inc=0.1)
        self.imfp_ctrl.SetDigits(2)
        self.imfp_ctrl.SetToolTip("Inelastic Mean Free Path\nAuto-calculated from TPP-2M when data loads")
        imfp_row.Add(self.imfp_ctrl, 1, wx.EXPAND)
        mat_sizer.Add(imfp_row, 0, wx.EXPAND | wx.ALL, 4)

        theta_row = wx.BoxSizer(wx.HORIZONTAL)
        theta_row.Add(wx.StaticText(mat_box, label="Angle θ (deg):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.theta_ctrl = wx.SpinCtrlDouble(mat_box, min=0, max=80, initial=0, inc=5)
        self.theta_ctrl.SetDigits(1)
        self.theta_ctrl.SetToolTip("Emission angle from surface normal\n0° = normal emission")
        theta_row.Add(self.theta_ctrl, 1, wx.EXPAND)
        mat_sizer.Add(theta_row, 0, wx.EXPAND | wx.ALL, 4)

        c_row = wx.BoxSizer(wx.HORIZONTAL)
        c_row.Add(wx.StaticText(mat_box, label="C (eV²):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.c_ctrl = wx.SpinCtrlDouble(mat_box, min=100, max=5000, initial=1643, inc=10)
        self.c_ctrl.SetDigits(2)
        self.c_ctrl.SetToolTip("Tougaard cross-section parameter\n1643 eV² for most metals/oxides")
        c_row.Add(self.c_ctrl, 1, wx.EXPAND)
        mat_sizer.Add(c_row, 0, wx.EXPAND | wx.ALL, 0)
        left_sizer.Add(mat_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Analysis Range
        range_box = wx.StaticBox(left_panel, label="Analysis Range (drag lines on plot)")
        range_sizer = wx.StaticBoxSizer(range_box, wx.VERTICAL)

        ps_row = wx.BoxSizer(wx.HORIZONTAL)
        ps_row.Add(wx.StaticText(range_box, label="Peak Start:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.peak_start_ctrl = wx.SpinCtrlDouble(range_box, min=0, max=2000, initial=0, inc=0.1)
        self.peak_start_ctrl.SetDigits(2)
        self.peak_start_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_range_change)
        ps_row.Add(self.peak_start_ctrl, 1, wx.EXPAND)
        range_sizer.Add(ps_row, 0, wx.EXPAND | wx.ALL, 4)

        pe_row = wx.BoxSizer(wx.HORIZONTAL)
        pe_row.Add(wx.StaticText(range_box, label="Peak End:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.peak_end_ctrl = wx.SpinCtrlDouble(range_box, min=0, max=2000, initial=0, inc=0.1)
        self.peak_end_ctrl.SetDigits(2)
        self.peak_end_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_range_change)
        pe_row.Add(self.peak_end_ctrl, 1, wx.EXPAND)
        range_sizer.Add(pe_row, 0, wx.EXPAND | wx.ALL, 4)

        bp_row = wx.BoxSizer(wx.HORIZONTAL)
        bp_row.Add(wx.StaticText(range_box, label="Bkg Point:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.bg_point_ctrl = wx.SpinCtrlDouble(range_box, min=0, max=2000, initial=0, inc=0.1)
        self.bg_point_ctrl.SetDigits(2)
        self.bg_point_ctrl.SetToolTip("Background measurement point\n~30 eV after peak centroid")
        self.bg_point_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_range_change)
        bp_row.Add(self.bg_point_ctrl, 1, wx.EXPAND)
        range_sizer.Add(bp_row, 0, wx.EXPAND | wx.ALL, 4)
        left_sizer.Add(range_sizer, 0, wx.EXPAND | wx.ALL, 0)

        # Results
        results_box = wx.StaticBox(left_panel, label="Results")
        results_sizer = wx.StaticBoxSizer(results_box, wx.VERTICAL)
        self.results_text = wx.TextCtrl(results_box, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 220))
        self.results_text.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        results_sizer.Add(self.results_text, 1, wx.EXPAND | wx.ALL, 2)
        copy_btn = wx.Button(results_box, label="Copy Results")
        copy_btn.Bind(wx.EVT_BUTTON, self.on_copy_results)
        results_sizer.Add(copy_btn, 0, wx.EXPAND | wx.ALL, 2)
        left_sizer.Add(results_sizer, 1, wx.EXPAND | wx.ALL, 3)

        # Analyse Button
        analyse_btn = wx.Button(left_panel, label="Analyse")
        analyse_btn.SetMinSize((-1, 35))
        analyse_btn.Bind(wx.EVT_BUTTON, self.on_analyse)
        analyse_btn.SetToolTip("Fit Tougaard background and calculate\nAp/B ratio and decay length")
        left_sizer.Add(analyse_btn, 0, wx.EXPAND | wx.ALL, 0)

        left_panel.SetSizer(left_sizer)

        # Right panel - Plot
        right_panel = wx.Panel(panel)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.figure = Figure(figsize=(6, 5), dpi=100)
        self.canvas = FigureCanvas(right_panel, -1, self.figure)
        right_sizer.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 0)
        right_panel.SetSizer(right_sizer)

        main_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, 0)
        main_sizer.Add(right_panel, 1, wx.EXPAND | wx.ALL, 0)
        panel.SetSizer(main_sizer)

        self.init_plot()
        self.canvas.mpl_connect('button_press_event', self.on_canvas_press)
        self.canvas.mpl_connect('button_release_event', self.on_canvas_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_canvas_motion)

    def init_plot(self):
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel('Binding Energy (eV)')
        self.ax.set_ylabel('Intensity (a.u.)')
        self.ax.ticklabel_format(axis='y', style='scientific', scilimits=(0, 0))
        self.figure.tight_layout()
        self.canvas.draw()

    def populate_core_levels(self):
        self.core_level_combo.Clear()
        if hasattr(self.parent, 'Data') and 'Core levels' in self.parent.Data:
            sheets = list(self.parent.Data['Core levels'].keys())
            self.core_level_combo.AppendItems(sheets)
            if sheets:
                if hasattr(self.parent, 'sheet_combobox'):
                    current = self.parent.sheet_combobox.GetValue()
                    if current in sheets:
                        self.core_level_combo.SetValue(current)
                    else:
                        self.core_level_combo.SetValue(sheets[0])
                else:
                    self.core_level_combo.SetValue(sheets[0])

    def calculate_imfp_tpp2m(self, kinetic_energy):
        """
        Calculate IMFP using TPP-2M formula with average matrix parameters.
        Same as AtomicConcentrations.calculate_imfp_tpp2m in Peak_Functions.py
        """
        N_v = 4.684
        rho = 6.767
        M = 137.51
        E_g = 0

        E_p = 28.8 * np.sqrt((N_v * rho) / M)
        U = N_v * rho / M

        beta = -0.10 + 0.944 / (E_p ** 2 + E_g ** 2) ** 0.5 + 0.069 * rho ** 0.1
        gamma = 0.191 * rho ** (-0.5)
        C = 1.97 - 0.91 * U
        D = 53.4 - 20.8 * U

        imfp = kinetic_energy / (E_p ** 2 * (
                beta * np.log(gamma * kinetic_energy) -
                (C / kinetic_energy) +
                (D / kinetic_energy ** 2))) / 10

        return imfp

    def on_core_level_change(self, event):
        sheet_name = self.core_level_combo.GetValue()
        if not sheet_name:
            return
        try:
            core_data = self.parent.Data['Core levels'][sheet_name]
            self.x_data = np.array(core_data['B.E.'])
            self.y_data = np.array(core_data['Raw Data'])
            self.current_sheet = sheet_name
            self.background = None
            self.fitted_B = None
            self.auto_detect_range()

            # Calculate IMFP using TPP-2M based on peak position
            peak_idx = np.argmax(self.y_data)
            peak_be = self.x_data[peak_idx]
            photon_energy = getattr(self.parent, 'photons', 1486.68)  # Default Al Ka
            kinetic_energy = photon_energy - peak_be
            if kinetic_energy > 0:
                imfp = self.calculate_imfp_tpp2m(kinetic_energy)
                self.imfp_ctrl.SetValue(imfp)

            self.update_plot()
            self.results_text.SetValue(f"Loaded: {sheet_name}\n"
                                       f"Peak BE: {peak_be:.2f} eV\n"
                                       f"KE: {kinetic_energy:.2f} eV\n"
                                       f"λ (TPP-2M): {imfp:.2f} nm\n\n"
                                       f"Click 'Analyse' to run analysis")
        except Exception as e:
            wx.MessageBox(f"Error loading data: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)

    def on_cross_section_change(self, event):
        cs_name = self.cross_section_combo.GetValue()
        if cs_name in self.CROSS_SECTIONS:
            self.c_ctrl.SetValue(self.CROSS_SECTIONS[cs_name]['C'])

    def auto_detect_range(self):
        if self.x_data is None:
            return
        peak_idx = np.argmax(self.y_data)
        peak_be = self.x_data[peak_idx]
        peak_start = np.clip(peak_be - 5, self.x_data.min(), self.x_data.max())
        peak_end = np.clip(peak_be + 5, self.x_data.min(), self.x_data.max())
        bg_point = np.clip(peak_be + 30, self.x_data.min(), self.x_data.max())
        self.peak_start_ctrl.SetValue(peak_start)
        self.peak_end_ctrl.SetValue(peak_end)
        self.bg_point_ctrl.SetValue(bg_point)

    def on_canvas_press(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        x_click = event.xdata
        peak_start = self.peak_start_ctrl.GetValue()
        peak_end = self.peak_end_ctrl.GetValue()
        bg_point = self.bg_point_ctrl.GetValue()
        xlim = self.ax.get_xlim()
        tol = abs(xlim[1] - xlim[0]) * 0.02

        if abs(x_click - peak_start) < tol:
            self.dragging_line = 'peak_start'
        elif abs(x_click - peak_end) < tol:
            self.dragging_line = 'peak_end'
        elif abs(x_click - bg_point) < tol:
            self.dragging_line = 'bg_point'

    def on_canvas_release(self, event):
        if self.dragging_line:
            self.dragging_line = None
            self.update_plot()

    def on_canvas_motion(self, event):
        if event.inaxes != self.ax or not self.dragging_line or event.xdata is None:
            return
        if self.dragging_line == 'peak_start':
            self.peak_start_ctrl.SetValue(event.xdata)
        elif self.dragging_line == 'peak_end':
            self.peak_end_ctrl.SetValue(event.xdata)
        elif self.dragging_line == 'bg_point':
            self.bg_point_ctrl.SetValue(event.xdata)
        self.update_plot()

    def on_range_change(self, event):
        self.update_plot()

    def update_plot(self):
        self.ax.clear()
        if self.x_data is None:
            self.canvas.draw()
            return

        self.ax.plot(self.x_data, self.y_data, 'b-', label='Raw Data', linewidth=1)
        if self.background is not None:
            self.ax.plot(self.x_data, self.background, 'r-', label='Tougaard Bkg', linewidth=1.5)

        peak_start = self.peak_start_ctrl.GetValue()
        peak_end = self.peak_end_ctrl.GetValue()
        bg_point = self.bg_point_ctrl.GetValue()

        self.ax.axvline(peak_start, color='green', linestyle='--', alpha=0.7, linewidth=1.5)
        self.ax.axvline(peak_end, color='green', linestyle='--', alpha=0.7, linewidth=1.5)
        self.ax.axvline(bg_point, color='orange', linestyle=':', alpha=0.7, linewidth=2)
        self.ax.axvspan(min(peak_start, peak_end), max(peak_start, peak_end), alpha=0.1, color='green')

        self.ax.set_xlabel('Binding Energy (eV)')
        self.ax.set_ylabel('Intensity (a.u.)')
        self.ax.set_title(self.current_sheet if self.current_sheet else '')
        self.ax.legend(loc='upper right', fontsize=8)
        self.ax.set_xlim(self.x_data.max(), self.x_data.min())
        self.ax.ticklabel_format(axis='y', style='scientific', scilimits=(0, 0))
        self.figure.tight_layout()
        self.canvas.draw()

    def calculate_u2_tougaard_background(self, x, y, C_value, target_be):
        """Calculate U2-Tougaard background."""
        baseline = np.mean(y[-5:])
        y_shifted = y - baseline
        target_idx = np.argmin(np.abs(x - target_be))
        target_intensity = y[target_idx]
        dx = np.mean(np.diff(x))

        def calculate_background(B_val):
            bg = np.zeros_like(y)
            for i in range(len(x)):
                E_prime_minus_E = x[i:] - x[i]
                K = B_val * E_prime_minus_E / ((C_value + E_prime_minus_E**2)**2 + 1e-10)
                bg[i] = np.trapz(K * y_shifted[i:], dx=dx)
            return bg + baseline

        def objective(B_val):
            try:
                bg = calculate_background(B_val)
                return (bg[target_idx] - target_intensity)**2
            except:
                return 1e10

        result = minimize_scalar(objective, bounds=(100, 1000000), method='bounded')
        B_fitted = result.x
        background = calculate_background(B_fitted)
        return background, B_fitted

    def on_analyse(self, event):
        """Run full Tougaard analysis."""
        if self.x_data is None:
            wx.MessageBox("Please select a core level first.", "No Data", wx.OK | wx.ICON_WARNING)
            return

        bg_point = self.bg_point_ctrl.GetValue()
        C = self.c_ctrl.GetValue()
        lambda_nm = self.imfp_ctrl.GetValue()
        theta_deg = self.theta_ctrl.GetValue()

        try:
            # Fit Tougaard background
            self.background, self.fitted_B = self.calculate_u2_tougaard_background(
                self.x_data, self.y_data, C, bg_point)

            # Calculate Ap/B
            peak_start, peak_end = self.peak_start_ctrl.GetValue(), self.peak_end_ctrl.GetValue()
            peak_min, peak_max = min(peak_start, peak_end), max(peak_start, peak_end)
            peak_mask = (self.x_data >= peak_min) & (self.x_data <= peak_max)
            x_peak, y_peak = self.x_data[peak_mask], self.y_data[peak_mask]

            if len(x_peak) < 3:
                wx.MessageBox("Peak region too small.", "Error", wx.OK | wx.ICON_WARNING)
                return

            sort_idx = np.argsort(x_peak)
            x_peak, y_peak = x_peak[sort_idx], y_peak[sort_idx]
            lin_bg = np.interp(x_peak, [x_peak[0], x_peak[-1]], [y_peak[0], y_peak[-1]])
            self.peak_area = np.abs(trapezoid(y_peak - lin_bg, x_peak))

            baseline = np.mean(self.y_data[-5:])
            bg_idx = np.argmin(np.abs(self.x_data - bg_point))
            self.B_increase = self.y_data[bg_idx] - baseline
            ap_b_ratio = self.peak_area / self.B_increase if self.B_increase > 0 else float('inf')

            # Calculate decay length
            cos_theta = np.cos(np.radians(theta_deg))
            B0 = self.B0_HOMOGENEOUS
            if abs(B0 - self.fitted_B) > 1e-10:
                L_lambda = (self.fitted_B / (B0 - self.fitted_B)) * cos_theta
                L_nm = L_lambda * lambda_nm
            else:
                L_lambda, L_nm = float('inf'), float('inf')

            # Generate report
            results = self.generate_report(ap_b_ratio, L_lambda, L_nm, lambda_nm)
            self.results_text.SetValue(results)

            # Update plot
            self.update_plot()
            self.ax.plot(x_peak, lin_bg, 'g--', linewidth=1.5)
            self.ax.fill_between(x_peak, lin_bg, y_peak, alpha=0.3, color='blue')
            self.ax.plot(bg_point, self.y_data[bg_idx], 'ro', markersize=8)
            self.canvas.draw()

        except Exception as e:
            wx.MessageBox(f"Error: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)

    def generate_report(self, ap_b_ratio, L_lambda, L_nm, lambda_nm):
        """Generate analysis report with interpretations."""
        B0 = self.B0_HOMOGENEOUS

        # Ap/B interpretation
        if ap_b_ratio > 30:
            apb_interp = "SURFACE LOCALIZED\nAtoms concentrated at surface (<1λ depth)"
        elif ap_b_ratio < 20:
            apb_interp = "SUBSURFACE/BURIED\nAtoms located below surface (>1λ depth)"
        else:
            apb_interp = "UNIFORM DISTRIBUTION\nAtoms distributed throughout probing depth"

        # Decay length interpretation - improved based on physics
        # L > 0: exponential decay INTO surface (surface enriched)
        # L < 0: exponential decay FROM surface (subsurface/buried)
        # |L| large: nearly uniform
        if abs(L_lambda) > 6:
            L_interp = "Nearly uniform depth distribution"
        elif L_lambda > 3:
            L_interp = "Surface enriched (gradual decay into bulk)"
        elif L_lambda > 0:
            L_interp = "Surface localized (sharp decay into bulk)"
        elif L_lambda > -3:
            L_interp = "Subsurface layer (concentration increases with depth)"
        else:
            L_interp = "Buried layer (atoms concentrated below surface)"

        # Physical meaning of negative L
        if L_lambda < 0:
            L_physical = f"Negative L means atoms are depleted at surface\nand enriched at depth ~{abs(L_nm):.1f} nm"
        else:
            L_physical = f"Positive L means atoms are enriched at surface\nwith decay length ~{L_nm:.1f} nm into bulk"

        # B1 indicator
        if self.fitted_B > B0 * 1.2:
            b_indicator = f"B > B₀: Surface enriched"
        elif self.fitted_B < B0 * 0.8:
            b_indicator = f"B < B₀: Subsurface/buried"
        else:
            b_indicator = f"B ≈ B₀: Near-homogeneous"

        report = f"""TOUGAARD DEPTH ANALYSIS
{'='*40}
Core Level: {self.current_sheet}

FITTED PARAMETERS
-----------------
B (fitted):  {self.fitted_B:.2f} eV²
B₀ (ref):    {B0:.2f} eV² (homogeneous)
C:           {self.c_ctrl.GetValue():.2f} eV²
IMFP (λ):    {lambda_nm:.2f} nm (TPP-2M)

B PARAMETER INDICATOR
---------------------
{b_indicator}

Ap/B RATIO METHOD
-----------------
Ap/B = {ap_b_ratio:.2f} eV
(Reference: D₀ ≈ 23 eV for homogeneous)

{apb_interp}

DECAY LENGTH METHOD
-------------------
L = {L_lambda:.2f}λ = {L_nm:.2f} nm

{L_interp}

{L_physical}
"""
        return report

    def on_copy_results(self, event):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.results_text.GetValue()))
            wx.TheClipboard.Close()