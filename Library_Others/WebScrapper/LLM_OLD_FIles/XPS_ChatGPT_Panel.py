# XPS_ChatGPT_Panel.py - GUI for XPS Assistant with all modes
# Location: libraries/LLMs/XPS_ChatGPT_Panel.py

import wx
import wx.adv
import threading
import os
import json
import re
import sys
import datetime
import numpy as np

try:
    from libraries.LLMs.XPS_ChatGPT import XPSChatGPT
except ImportError:
    from XPS_ChatGPT import XPSChatGPT

try:
    from libraries.LLMs.XPS_RunPod import XPSRunPod

    RUNPOD_AVAILABLE = True
except ImportError:
    try:
        from XPS_RunPod import XPSRunPod

        RUNPOD_AVAILABLE = True
    except ImportError:
        RUNPOD_AVAILABLE = False

try:
    from libraries.LLMs.XPS_Assistant import XPSAssistant

    ASSISTANT_AVAILABLE = True
except ImportError:
    ASSISTANT_AVAILABLE = False


class XPSAssistantFrame(wx.Frame):
    """Main frame for XPS Assistant with proper menu bar"""

    def __init__(self, parent, window):
        super().__init__(parent, title="XPS Assistant", size=(900, 750))
        self.window = window
        self._create_menu_bar()
        self.panel = XPSChatGPTPanel(self, window)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Centre()

    def _create_menu_bar(self):
        """Create the menu bar"""
        menubar = wx.MenuBar()

        # Edit Menu
        edit_menu = wx.Menu()
        config_item = edit_menu.Append(wx.ID_PREFERENCES, "Configuration...\tCtrl+,")
        menubar.Append(edit_menu, "&Edit")

        # Teach Menu
        teach_menu = wx.Menu()
        self.teach_item = teach_menu.Append(wx.ID_ANY, "Teach Correction...\tCtrl+T")
        self.view_learning_item = teach_menu.Append(wx.ID_ANY, "View Learning...")
        self.clear_learning_item = teach_menu.Append(wx.ID_ANY, "Clear Learning...")
        teach_menu.AppendSeparator()
        self.open_folder_item = teach_menu.Append(wx.ID_ANY, "Open Learning Folder")
        menubar.Append(teach_menu, "&Teach")

        # Help Menu
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "About XPS Assistant")
        help_menu.AppendSeparator()
        openai_key_item = help_menu.Append(wx.ID_ANY, "Get OpenAI API Key...")
        runpod_key_item = help_menu.Append(wx.ID_ANY, "Get RunPod API Key...")
        hf_key_item = help_menu.Append(wx.ID_ANY, "Get Hugging Face Token...")
        menubar.Append(help_menu, "&Help")

        self.SetMenuBar(menubar)

        # Bind events
        self.Bind(wx.EVT_MENU, self.on_config, config_item)
        self.Bind(wx.EVT_MENU, self.on_teach, self.teach_item)
        self.Bind(wx.EVT_MENU, self.on_view_learning, self.view_learning_item)
        self.Bind(wx.EVT_MENU, self.on_clear_learning, self.clear_learning_item)
        self.Bind(wx.EVT_MENU, self.on_open_folder, self.open_folder_item)
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        self.Bind(wx.EVT_MENU, lambda e: wx.LaunchDefaultBrowser("https://platform.openai.com/api-keys"), openai_key_item)
        self.Bind(wx.EVT_MENU, lambda e: wx.LaunchDefaultBrowser("https://www.runpod.io/console/user/settings"), runpod_key_item)
        self.Bind(wx.EVT_MENU, lambda e: wx.LaunchDefaultBrowser("https://huggingface.co/settings/tokens"), hf_key_item)

    def on_config(self, event):
        self.panel.on_open_config(event)

    def on_teach(self, event):
        self.panel.on_teach(event)

    def on_view_learning(self, event):
        self.panel.on_view_learning(event)

    def on_clear_learning(self, event):
        self.panel.on_clear_learning(event)

    def on_open_folder(self, event):
        folder = os.path.expanduser("~/.khervefitting")
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')

    def on_about(self, event):
        self.panel.on_about(event)


class XPSChatGPTPanel(wx.Panel):
    """Main panel for XPS Assistant"""

    LEARNING_PATH = os.path.expanduser("~/.khervefitting/xps_learning.json")
    CONFIG_PATH = os.path.expanduser("~/.khervefitting/chatgpt_config.json")

    def __init__(self, parent, window):
        super().__init__(parent)
        self.window = window
        self.assistant = XPSChatGPT()
        self.runpod_assistant = None
        self.advanced_assistant = None
        self.current_mode = "simple"
        self.last_response = ""
        self.last_query_context = {}
        self.suggested_peaks = []
        self._create_ui()
        self._load_config()
        self._populate_core_levels()

    def _create_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Mode Selection
        mode_box = wx.StaticBox(self, label="Assistant Mode")
        mode_sizer = wx.StaticBoxSizer(mode_box, wx.HORIZONTAL)

        self.simple_radio = wx.RadioButton(self, label="Simple (ChatGPT)", style=wx.RB_GROUP)
        self.simple_radio.SetToolTip("Local NIST DB + ChatGPT API")
        self.simple_radio.Bind(wx.EVT_RADIOBUTTON, self.on_mode_changed)
        mode_sizer.Add(self.simple_radio, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.advanced_radio = wx.RadioButton(self, label="Advanced (GPT-4o)")
        self.advanced_radio.SetToolTip("OpenAI Assistant with file search")
        self.advanced_radio.Bind(wx.EVT_RADIOBUTTON, self.on_mode_changed)
        mode_sizer.Add(self.advanced_radio, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.runpod_radio = wx.RadioButton(self, label="RunPod (Your LLM)")
        self.runpod_radio.SetToolTip("Self-hosted Llama on RunPod")
        self.runpod_radio.Bind(wx.EVT_RADIOBUTTON, self.on_mode_changed)
        self.runpod_radio.Enable(RUNPOD_AVAILABLE)
        mode_sizer.Add(self.runpod_radio, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        mode_sizer.AddStretchSpacer()
        self.mode_status = wx.StaticText(self, label="")
        mode_sizer.Add(self.mode_status, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        main_sizer.Add(mode_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Core Level Selection
        cl_box = wx.StaticBox(self, label="Data Selection")
        cl_sizer = wx.StaticBoxSizer(cl_box, wx.VERTICAL)

        cl_row = wx.BoxSizer(wx.HORIZONTAL)
        cl_row.Add(wx.StaticText(self, label="Core Level:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.core_level_combo = wx.ComboBox(self, style=wx.CB_READONLY, size=(250, -1))
        self.core_level_combo.Bind(wx.EVT_COMBOBOX, self.on_core_level_changed)
        cl_row.Add(self.core_level_combo, 1, wx.EXPAND | wx.RIGHT, 10)

        self.refresh_btn = wx.Button(self, label="↻", size=(30, -1))
        self.refresh_btn.Bind(wx.EVT_BUTTON, lambda e: self._populate_core_levels())
        cl_row.Add(self.refresh_btn, 0)
        cl_sizer.Add(cl_row, 0, wx.EXPAND | wx.ALL, 5)

        self.data_info = wx.StaticText(self, label="No data loaded")
        self.data_info.SetForegroundColour(wx.Colour(100, 100, 100))
        cl_sizer.Add(self.data_info, 0, wx.LEFT | wx.BOTTOM, 5)

        main_sizer.Add(cl_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Peak Identification
        id_box = wx.StaticBox(self, label="Peak Identification")
        id_sizer = wx.StaticBoxSizer(id_box, wx.VERTICAL)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        row1.Add(wx.StaticText(self, label="Element:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.element_ctrl = wx.TextCtrl(self, size=(50, -1))
        self.element_ctrl.SetHint("Fe")
        row1.Add(self.element_ctrl, 0, wx.RIGHT, 15)

        row1.Add(wx.StaticText(self, label="Orbital:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.orbital_ctrl = wx.TextCtrl(self, size=(60, -1))
        self.orbital_ctrl.SetHint("2p3/2")
        row1.Add(self.orbital_ctrl, 0, wx.RIGHT, 15)

        row1.Add(wx.StaticText(self, label="BE (eV):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.be_ctrl = wx.TextCtrl(self, size=(80, -1))
        self.be_ctrl.SetHint("710.9")
        row1.Add(self.be_ctrl, 0, wx.RIGHT, 15)

        self.identify_btn = wx.Button(self, label="Identify Peak")
        self.identify_btn.Bind(wx.EVT_BUTTON, self.on_identify)
        row1.Add(self.identify_btn, 0, wx.RIGHT, 10)

        self.constraints_btn = wx.Button(self, label="Get Fitting Constraints")
        self.constraints_btn.Bind(wx.EVT_BUTTON, self.on_get_constraints)
        row1.Add(self.constraints_btn, 0)

        id_sizer.Add(row1, 0, wx.ALL, 5)
        main_sizer.Add(id_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Analyze Section
        analyze_box = wx.StaticBox(self, label="Analyze Selected Core Level")
        analyze_sizer = wx.StaticBoxSizer(analyze_box, wx.VERTICAL)

        sample_row = wx.BoxSizer(wx.HORIZONTAL)
        sample_row.Add(wx.StaticText(self, label="Sample info:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.sample_ctrl = wx.TextCtrl(self, size=(400, -1))
        self.sample_ctrl.SetHint("Optional: e.g., Fe foil oxidized at 400°C")
        sample_row.Add(self.sample_ctrl, 1, wx.EXPAND)
        analyze_sizer.Add(sample_row, 0, wx.EXPAND | wx.ALL, 5)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.analyze_btn = wx.Button(self, label="Analyze Spectrum")
        self.analyze_btn.Bind(wx.EVT_BUTTON, self.on_analyze)
        btn_row.Add(self.analyze_btn, 0, wx.RIGHT, 10)

        self.suggest_btn = wx.Button(self, label="Suggest Peak Fitting")
        self.suggest_btn.Bind(wx.EVT_BUTTON, self.on_suggest_fitting)
        btn_row.Add(self.suggest_btn, 0, wx.RIGHT, 10)

        self.apply_btn = wx.Button(self, label="Apply Suggested Fit")
        self.apply_btn.Bind(wx.EVT_BUTTON, self.on_apply_fitting)
        self.apply_btn.Enable(False)
        btn_row.Add(self.apply_btn, 0)

        analyze_sizer.Add(btn_row, 0, wx.LEFT | wx.BOTTOM, 5)
        main_sizer.Add(analyze_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Custom Question
        q_box = wx.StaticBox(self, label="Ask a Question")
        q_sizer = wx.StaticBoxSizer(q_box, wx.VERTICAL)

        self.question_ctrl = wx.TextCtrl(self, size=(-1, 50), style=wx.TE_MULTILINE)
        self.question_ctrl.SetHint("Ask any XPS question...")
        q_sizer.Add(self.question_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        self.ask_btn = wx.Button(self, label="Ask")
        self.ask_btn.Bind(wx.EVT_BUTTON, self.on_ask)
        q_sizer.Add(self.ask_btn, 0, wx.LEFT | wx.BOTTOM, 5)

        main_sizer.Add(q_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Response Area
        main_sizer.Add(wx.StaticText(self, label="Response:"), 0, wx.LEFT | wx.TOP, 5)
        self.response_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, 180))
        self.response_ctrl.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        main_sizer.Add(self.response_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        # Feedback Section
        fb_box = wx.StaticBox(self, label="Feedback")
        fb_sizer = wx.StaticBoxSizer(fb_box, wx.HORIZONTAL)

        self.thumbs_up = wx.Button(self, label="👍 Good", size=(80, -1))
        self.thumbs_up.Bind(wx.EVT_BUTTON, lambda e: self.on_feedback(True))
        fb_sizer.Add(self.thumbs_up, 0, wx.ALL, 5)

        self.thumbs_down = wx.Button(self, label="👎 Bad", size=(80, -1))
        self.thumbs_down.Bind(wx.EVT_BUTTON, lambda e: self.on_feedback(False))
        fb_sizer.Add(self.thumbs_down, 0, wx.ALL, 5)

        fb_sizer.AddStretchSpacer()
        self.status_label = wx.StaticText(self, label="Ready")
        self.status_label.SetForegroundColour(wx.Colour(100, 100, 100))
        fb_sizer.Add(self.status_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        main_sizer.Add(fb_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(main_sizer)

    def _load_config(self):
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                key = config.get('api_key', '')
                if key:
                    self.assistant.set_api_key(key)
                    self._update_status("API key loaded", "green")
                self.assistant.model = config.get('model', 'gpt-4o-mini')
                mode = config.get('mode', 'simple')
                if mode == 'advanced':
                    self.advanced_radio.SetValue(True)
                    self.current_mode = 'advanced'
                elif mode == 'runpod' and RUNPOD_AVAILABLE:
                    self.runpod_radio.SetValue(True)
                    self.current_mode = 'runpod'
                if RUNPOD_AVAILABLE:
                    self.runpod_assistant = XPSRunPod()
                    if self.runpod_assistant.is_ready():
                        self.mode_status.SetLabel("RunPod ✓")
                        self.mode_status.SetForegroundColour(wx.Colour(0, 128, 0))
            except Exception as e:
                print(f"Config error: {e}")

    def _save_config(self, **kwargs):
        os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
        config = {}
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, 'r') as f:
                    config = json.load(f)
            except:
                pass
        config.update(kwargs)
        config['mode'] = self.current_mode
        with open(self.CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)

    def _populate_core_levels(self):
        self.core_level_combo.Clear()
        try:
            if hasattr(self.window, 'Data') and 'Core levels' in self.window.Data:
                sheets = list(self.window.Data['Core levels'].keys())
                for s in sheets:
                    self.core_level_combo.Append(s)
                if sheets:
                    current = getattr(self.window, 'sheet_combobox', None)
                    if current and current.GetValue() in sheets:
                        self.core_level_combo.SetValue(current.GetValue())
                    else:
                        self.core_level_combo.SetSelection(0)
                    self._update_data_info()
        except Exception as e:
            print(f"Error: {e}")

    def _update_data_info(self):
        sheet = self.core_level_combo.GetValue()
        if not sheet:
            self.data_info.SetLabel("No data loaded")
            return
        try:
            data = self.window.Data['Core levels'].get(sheet, {})
            x = None
            for k in ['B.E.', 'BE', 'Binding Energy', 'K.E.', 'KE']:
                if k in data:
                    x = data[k]
                    break
            peaks = 0
            if 'Fitting' in data and 'Peaks' in data['Fitting']:
                peaks = len(data['Fitting']['Peaks'])
            if x is not None:
                info = f"Points: {len(x)}, Range: {min(x):.2f}-{max(x):.2f} eV"
                info += f", Peaks: {peaks}" if peaks else " (No peaks)"
                self.data_info.SetLabel(info)
        except Exception as e:
            self.data_info.SetLabel(f"Error: {e}")

    def _update_status(self, msg, color="black"):
        self.status_label.SetLabel(msg)
        colors = {"green": (0, 128, 0), "red": (200, 0, 0), "blue": (0, 0, 150), "orange": (200, 100, 0), "black": (0, 0, 0)}
        self.status_label.SetForegroundColour(wx.Colour(*colors.get(color, (0, 0, 0))))

    def on_mode_changed(self, event):
        if self.simple_radio.GetValue():
            self.current_mode = "simple"
            self._update_status("Simple mode", "blue")
        elif self.advanced_radio.GetValue():
            self.current_mode = "advanced"
            self._update_status("Advanced mode", "blue")
        elif self.runpod_radio.GetValue():
            self.current_mode = "runpod"
            if self.runpod_assistant and self.runpod_assistant.is_ready():
                self._update_status("RunPod mode", "blue")
            else:
                self._update_status("RunPod - setup in Config", "orange")
        self._save_config()

    def on_core_level_changed(self, event):
        self._update_data_info()
        sheet = self.core_level_combo.GetValue()
        if sheet:
            match = re.match(r'([A-Z][a-z]?)\s*(\d[spdf]\d?/?[\d/]*)', sheet)
            if match:
                self.element_ctrl.SetValue(match.group(1))
                self.orbital_ctrl.SetValue(match.group(2))

    def _get_assistant(self):
        if self.current_mode == "runpod" and self.runpod_assistant and self.runpod_assistant.is_ready():
            return self.runpod_assistant
        elif self.current_mode == "advanced" and self.advanced_assistant:
            return self.advanced_assistant
        return self.assistant

    def on_identify(self, event):
        elem = self.element_ctrl.GetValue().strip()
        orb = self.orbital_ctrl.GetValue().strip()
        be_text = self.be_ctrl.GetValue().strip()
        if not elem or not orb or not be_text:
            wx.MessageBox("Enter element, orbital, and BE", "Missing", wx.OK)
            return
        try:
            be = float(be_text)
        except:
            wx.MessageBox("Invalid BE value", "Error", wx.OK)
            return
        self.last_query_context = {'type': 'identify', 'element': elem, 'orbital': orb, 'be': be}
        self._run_query(lambda: self._get_assistant().identify_peak(elem, orb, be))

    def on_get_constraints(self, event):
        elem = self.element_ctrl.GetValue().strip()
        orb = self.orbital_ctrl.GetValue().strip()
        if not elem or not orb:
            wx.MessageBox("Enter element and orbital", "Missing", wx.OK)
            return
        self.last_query_context = {'type': 'constraints', 'element': elem, 'orbital': orb}
        self._run_query(lambda: self._get_assistant().get_fitting_advice(elem, orb))

    def on_analyze(self, event):
        sheet = self.core_level_combo.GetValue()
        if not sheet:
            wx.MessageBox("Select a core level", "Missing", wx.OK)
            return
        peaks, core_level, summary = self._get_sheet_data(sheet)
        sample = self.sample_ctrl.GetValue().strip() or None
        self.last_query_context = {'type': 'analyze', 'sheet': sheet}
        self._run_query(lambda: self._get_assistant().analyze_spectrum(core_level, peaks, sample, summary))

    def on_suggest_fitting(self, event):
        sheet = self.core_level_combo.GetValue()
        if not sheet:
            wx.MessageBox("Select a core level", "Missing", wx.OK)
            return
        peaks, core_level, summary = self._get_sheet_data(sheet)
        sample = self.sample_ctrl.GetValue().strip() or None
        self.last_query_context = {'type': 'suggest', 'sheet': sheet}
        self._run_query(lambda: self._get_assistant().suggest_peak_fitting(core_level, summary, sample))

    def on_apply_fitting(self, event):
        if not self.suggested_peaks:
            return
        sheet = self.core_level_combo.GetValue()
        try:
            self._apply_peaks(sheet, self.suggested_peaks)
            wx.MessageBox(f"Applied {len(self.suggested_peaks)} peaks", "Success", wx.OK)
            self.apply_btn.Enable(False)
            self._update_data_info()
        except Exception as e:
            wx.MessageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def on_ask(self, event):
        q = self.question_ctrl.GetValue().strip()
        if not q:
            return
        elem = self.element_ctrl.GetValue().strip() or None
        orb = self.orbital_ctrl.GetValue().strip() or None
        self.last_query_context = {'type': 'question', 'question': q}
        asst = self._get_assistant()
        if hasattr(asst, 'ask_question'):
            self._run_query(lambda: asst.ask_question(q, elem, orb))
        else:
            self._run_query(lambda: asst.ask(q))

    def _run_query(self, func):
        self.response_ctrl.SetValue("Processing...")
        self._update_status("Processing...", "blue")
        self._enable_buttons(False)

        def run():
            try:
                result = func()
            except Exception as e:
                result = f"Error: {e}"
            wx.CallAfter(self._show_result, result)

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _show_result(self, result):
        self.last_response = result
        self.response_ctrl.SetValue(result)
        self._update_status("Done", "green")
        self._enable_buttons(True)
        if self.last_query_context.get('type') == 'suggest':
            self._parse_suggestions(result)

    def _parse_suggestions(self, result):
        self.suggested_peaks = []
        pattern = r'(\d+\.?\d*)\s*eV.*?FWHM[:\s]*(\d+\.?\d*)'
        for pos, fwhm in re.findall(pattern, result, re.I):
            self.suggested_peaks.append({'position': float(pos), 'fwhm': float(fwhm)})
        self.apply_btn.Enable(bool(self.suggested_peaks))

    def _enable_buttons(self, enable):
        for btn in [self.identify_btn, self.constraints_btn, self.analyze_btn, self.suggest_btn, self.ask_btn]:
            btn.Enable(enable)

    def _get_sheet_data(self, sheet):
        peaks, core_level, summary = [], sheet, ""
        try:
            data = self.window.Data['Core levels'].get(sheet, {})
            core_level = data.get('Core Level', sheet)
            x, y = None, None
            for k in ['B.E.', 'BE', 'Binding Energy']:
                if k in data:
                    x = np.array(data[k])
                    break
            for k in ['Raw Data', 'Intensity', 'Counts', 'CPS']:
                if k in data:
                    y = np.array(data[k])
                    break
            if x is not None and y is not None:
                summary = f"Range: {min(x):.2f}-{max(x):.2f} eV, Intensity: {min(y):.2f}-{max(y):.2f}"
            if 'Fitting' in data and 'Peaks' in data['Fitting']:
                for label, p in data['Fitting']['Peaks'].items():
                    peaks.append({
                        'name': label,
                        'position': float(f"{p.get('Position', 0):.2f}"),
                        'fwhm': float(f"{p.get('FWHM', 0):.2f}"),
                        'height': float(f"{p.get('Height', 0):.2f}"),
                        'area': float(f"{p.get('Area', 0):.2f}")
                    })
        except Exception as e:
            print(f"Error: {e}")
        return peaks, core_level, summary

    def _apply_peaks(self, sheet, peaks):
        data = self.window.Data['Core levels'].get(sheet, {})
        if 'Fitting' not in data:
            data['Fitting'] = {}
        if 'Peaks' not in data['Fitting']:
            data['Fitting']['Peaks'] = {}
        for i, p in enumerate(peaks):
            label = f"Peak_{i + 1}"
            data['Fitting']['Peaks'][label] = {
                'Position': float(f"{p['position']:.2f}"),
                'Height': 1000.0,
                'FWHM': float(f"{p['fwhm']:.2f}"),
                'L/G': 30.0,
                'Area': 1000.0,
                'Fitting Model': 'GL'
            }
        if hasattr(self.window, 'clear_and_replot'):
            self.window.clear_and_replot()

    # === Config Dialog ===
    def on_open_config(self, event):
        dlg = ConfigDialog(self, self.assistant, self.runpod_assistant)
        if dlg.ShowModal() == wx.ID_OK:
            vals = dlg.get_values()
            if vals.get('openai_key'):
                self.assistant.set_api_key(vals['openai_key'])
                self._save_config(api_key=vals['openai_key'])
            if vals.get('model'):
                self.assistant.model = vals['model']
                self._save_config(model=vals['model'])
            if vals.get('runpod_key') and vals.get('runpod_endpoint'):
                if not self.runpod_assistant and RUNPOD_AVAILABLE:
                    self.runpod_assistant = XPSRunPod()
                if self.runpod_assistant:
                    self.runpod_assistant.save_config(vals['runpod_key'], vals['runpod_endpoint'])
            self._update_status("Config saved", "green")
        dlg.Destroy()

    def on_about(self, event):
        msg = """XPS Assistant for KherveFitting

MODES:
• Simple: Local NIST DB + ChatGPT
• Advanced: GPT-4o with file search  
• RunPod: Your own fine-tuned LLM

Learning files: ~/.khervefitting/

Created by Gwilherm Kerherve
Imperial College London"""
        wx.MessageBox(msg, "About", wx.OK | wx.ICON_INFORMATION)

    # === Learning/Teaching ===
    def on_feedback(self, positive):
        if not self.last_response:
            wx.MessageBox("Make a query first", "No Query", wx.OK)
            return
        if positive:
            self._save_learning(self.last_query_context, self.last_response, positive=True)
            self._update_status("Thanks! ✓", "green")
        else:
            self._update_status("Use Teach > Teach Correction", "orange")

    def on_teach(self, event):
        if not self.last_response:
            wx.MessageBox("Make a query first", "No Query", wx.OK)
            return
        dlg = TeachDialog(self, self.last_query_context, self.last_response)
        if dlg.ShowModal() == wx.ID_OK:
            correction = dlg.get_correction()
            if correction:
                self._save_learning(self.last_query_context, self.last_response, correction=correction)
                self._update_status("Correction saved ✓", "green")
        dlg.Destroy()

    def on_view_learning(self, event):
        if not os.path.exists(self.LEARNING_PATH):
            wx.MessageBox(f"No learning data.\n\nPath: {self.LEARNING_PATH}", "Learning", wx.OK)
            return
        try:
            with open(self.LEARNING_PATH, 'r') as f:
                data = json.load(f)
            dlg = LearningDialog(self, data)
            dlg.ShowModal()
            dlg.Destroy()
        except Exception as e:
            wx.MessageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def on_clear_learning(self, event):
        if wx.MessageBox("Clear all learning?", "Confirm", wx.YES_NO | wx.ICON_WARNING) == wx.YES:
            if os.path.exists(self.LEARNING_PATH):
                os.remove(self.LEARNING_PATH)
            wx.MessageBox("Cleared", "Done", wx.OK)

    def _save_learning(self, ctx, resp, positive=False, correction=None):
        os.makedirs(os.path.dirname(self.LEARNING_PATH), exist_ok=True)
        data = {'corrections': [], 'positive': []}
        if os.path.exists(self.LEARNING_PATH):
            try:
                with open(self.LEARNING_PATH, 'r') as f:
                    data = json.load(f)
            except:
                pass
        entry = {'context': ctx, 'response': resp[:500], 'time': datetime.datetime.now().isoformat()}
        if positive:
            data.setdefault('positive', []).append(entry)
        elif correction:
            entry['correction'] = correction
            data.setdefault('corrections', []).append(entry)
        with open(self.LEARNING_PATH, 'w') as f:
            json.dump(data, f, indent=2)


class ConfigDialog(wx.Dialog):
    def __init__(self, parent, assistant, runpod=None):
        super().__init__(parent, title="Configuration", size=(500, 400))
        self.assistant = assistant
        self.runpod = runpod
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        nb = wx.Notebook(panel)

        # OpenAI Tab
        openai_p = wx.Panel(nb)
        openai_s = wx.BoxSizer(wx.VERTICAL)
        openai_s.Add(wx.StaticText(openai_p, label="OpenAI API Key:"), 0, wx.ALL, 10)
        self.key_ctrl = wx.TextCtrl(openai_p, style=wx.TE_PASSWORD, size=(400, -1))
        if assistant.api_key:
            self.key_ctrl.SetValue(assistant.api_key)
        openai_s.Add(self.key_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        openai_s.Add(wx.StaticText(openai_p, label="Model:"), 0, wx.ALL, 10)
        self.model_choice = wx.Choice(openai_p, choices=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"])
        models = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        if assistant.model in models:
            self.model_choice.SetSelection(models.index(assistant.model))
        openai_s.Add(self.model_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        openai_p.SetSizer(openai_s)
        nb.AddPage(openai_p, "OpenAI")

        # RunPod Tab
        runpod_p = wx.Panel(nb)
        runpod_s = wx.BoxSizer(wx.VERTICAL)
        runpod_s.Add(wx.StaticText(runpod_p, label="RunPod API Key:"), 0, wx.ALL, 10)
        self.rp_key = wx.TextCtrl(runpod_p, style=wx.TE_PASSWORD, size=(400, -1))
        if runpod and runpod.api_key:
            self.rp_key.SetValue(runpod.api_key)
        runpod_s.Add(self.rp_key, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        runpod_s.Add(wx.StaticText(runpod_p, label="Endpoint ID:"), 0, wx.ALL, 10)
        self.rp_endpoint = wx.TextCtrl(runpod_p, size=(400, -1))
        if runpod and runpod.endpoint_id:
            self.rp_endpoint.SetValue(runpod.endpoint_id)
        runpod_s.Add(self.rp_endpoint, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        test_btn = wx.Button(runpod_p, label="Test Connection")
        test_btn.Bind(wx.EVT_BUTTON, self.on_test_runpod)
        runpod_s.Add(test_btn, 0, wx.ALL, 10)
        self.rp_status = wx.StaticText(runpod_p, label="")
        runpod_s.Add(self.rp_status, 0, wx.LEFT | wx.RIGHT, 10)
        runpod_p.SetSizer(runpod_s)
        nb.AddPage(runpod_p, "RunPod")

        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 10)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(wx.Button(panel, wx.ID_OK, "Save"))
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        panel.SetSizer(sizer)

    def on_test_runpod(self, event):
        key = self.rp_key.GetValue().strip()
        endpoint = self.rp_endpoint.GetValue().strip()
        if not key or not endpoint:
            self.rp_status.SetLabel("Enter key and endpoint")
            return
        self.rp_status.SetLabel("Testing...")
        if RUNPOD_AVAILABLE:
            test = XPSRunPod(key, endpoint)
            ok, msg = test.test_connection()
            self.rp_status.SetLabel("✓ Connected!" if ok else f"✗ {msg}")
            self.rp_status.SetForegroundColour(wx.Colour(0, 128, 0) if ok else wx.Colour(200, 0, 0))

    def get_values(self):
        models = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        return {
            'openai_key': self.key_ctrl.GetValue().strip(),
            'model': models[self.model_choice.GetSelection()],
            'runpod_key': self.rp_key.GetValue().strip(),
            'runpod_endpoint': self.rp_endpoint.GetValue().strip()
        }


class TeachDialog(wx.Dialog):
    def __init__(self, parent, ctx, resp):
        super().__init__(parent, title="Teach Correction", size=(600, 450))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label="Original response:"), 0, wx.ALL, 5)
        orig = wx.TextCtrl(panel, value=resp[:400], style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
        sizer.Add(orig, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Add(wx.StaticText(panel, label="Correct answer:"), 0, wx.ALL, 5)
        self.correction = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 150))
        sizer.Add(self.correction, 1, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(wx.Button(panel, wx.ID_OK, "Save"))
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        panel.SetSizer(sizer)

    def get_correction(self):
        return self.correction.GetValue().strip()


class LearningDialog(wx.Dialog):
    def __init__(self, parent, data):
        super().__init__(parent, title="Learning Data", size=(650, 450))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        nb = wx.Notebook(panel)

        # Corrections
        corr_p = wx.Panel(nb)
        corr_s = wx.BoxSizer(wx.VERTICAL)
        corrs = data.get('corrections', [])
        text = f"Corrections: {len(corrs)}\n\n"
        for c in corrs[-20:]:
            text += f"---\n{c.get('time', '')}\n{c.get('correction', '')[:200]}\n\n"
        ctrl = wx.TextCtrl(corr_p, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY)
        corr_s.Add(ctrl, 1, wx.EXPAND | wx.ALL, 5)
        corr_p.SetSizer(corr_s)
        nb.AddPage(corr_p, f"Corrections ({len(corrs)})")

        # Positive
        pos_p = wx.Panel(nb)
        pos_s = wx.BoxSizer(wx.VERTICAL)
        pos = data.get('positive', [])
        text2 = f"Positive: {len(pos)}\n\n"
        for p in pos[-20:]:
            text2 += f"---\n{p.get('time', '')}\n"
        ctrl2 = wx.TextCtrl(pos_p, value=text2, style=wx.TE_MULTILINE | wx.TE_READONLY)
        pos_s.Add(ctrl2, 1, wx.EXPAND | wx.ALL, 5)
        pos_p.SetSizer(pos_s)
        nb.AddPage(pos_p, f"Positive ({len(pos)})")

        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 10)
        close = wx.Button(panel, wx.ID_CLOSE, "Close")
        close.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        sizer.Add(close, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        panel.SetSizer(sizer)


def open_xps_assistant(parent, window):
    """Open the XPS Assistant frame"""
    frame = XPSAssistantFrame(parent, window)
    frame.Show()
    return frame