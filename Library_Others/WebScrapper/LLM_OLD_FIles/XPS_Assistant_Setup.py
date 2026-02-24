# XPS_Assistant_Setup.py - Setup dialog for XPS Assistant
# Location: libraries/LLMs/XPS_Assistant_Setup.py

import wx
import os
import threading


class AssistantSetupDialog(wx.Dialog):
    """Dialog to set up the XPS Assistant with knowledge files"""

    def __init__(self, parent, assistant):
        super().__init__(parent, title="Setup XPS Assistant", size=(550, 400))
        self.assistant = assistant
        self.setup_complete = False

        self._create_ui()

    def _create_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        intro = wx.StaticText(panel, label="""
This will create a specialized XPS Assistant that has access to your 
NIST database and can search it to answer questions accurately.

The assistant is stored on OpenAI's servers and persists between sessions.
Setup only needs to be done once (or when you update your database).
        """)
        sizer.Add(intro, 0, wx.ALL, 10)

        # NIST file selection
        sizer.Add(wx.StaticText(panel, label="NIST Database File (required):"), 0, wx.LEFT | wx.TOP, 10)

        nist_row = wx.BoxSizer(wx.HORIZONTAL)
        self.nist_path_ctrl = wx.TextCtrl(panel, size=(400, -1))
        self.nist_path_ctrl.SetHint("Path to NIST_BE.xlsx or NIST_BE.csv")
        nist_row.Add(self.nist_path_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)

        nist_browse_btn = wx.Button(panel, label="Browse...")
        nist_browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_nist)
        nist_row.Add(nist_browse_btn, 0)

        sizer.Add(nist_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Rules file selection (optional)
        sizer.Add(wx.StaticText(panel, label="Fitting Rules File (optional):"), 0, wx.LEFT | wx.TOP, 10)

        rules_row = wx.BoxSizer(wx.HORIZONTAL)
        self.rules_path_ctrl = wx.TextCtrl(panel, size=(400, -1))
        self.rules_path_ctrl.SetHint("Path to fitting rules (txt, pdf, or docx)")
        rules_row.Add(self.rules_path_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)

        rules_browse_btn = wx.Button(panel, label="Browse...")
        rules_browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_rules)
        rules_row.Add(rules_browse_btn, 0)

        sizer.Add(rules_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Progress
        sizer.Add(wx.StaticText(panel, label="Progress:"), 0, wx.LEFT | wx.TOP, 10)

        self.progress_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
        sizer.Add(self.progress_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.setup_btn = wx.Button(panel, label="Setup Assistant")
        self.setup_btn.Bind(wx.EVT_BUTTON, self.on_setup)
        btn_sizer.Add(self.setup_btn, 0, wx.RIGHT, 10)

        self.delete_btn = wx.Button(panel, label="Delete Existing")
        self.delete_btn.Bind(wx.EVT_BUTTON, self.on_delete)
        self.delete_btn.Enable(self.assistant.is_ready())
        btn_sizer.Add(self.delete_btn, 0, wx.RIGHT, 10)

        close_btn = wx.Button(panel, wx.ID_CLOSE, label="Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK if self.setup_complete else wx.ID_CANCEL))
        btn_sizer.Add(close_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Status
        if self.assistant.is_ready():
            self.progress_ctrl.SetValue(f"Existing assistant found: {self.assistant.assistant_id}\n")

        panel.SetSizer(sizer)

    def on_browse_nist(self, event):
        with wx.FileDialog(self, "Select NIST Database", wildcard="Excel/CSV files (*.xlsx;*.csv)|*.xlsx;*.csv",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.nist_path_ctrl.SetValue(dlg.GetPath())

    def on_browse_rules(self, event):
        with wx.FileDialog(self, "Select Rules File", wildcard="All supported (*.txt;*.pdf;*.docx)|*.txt;*.pdf;*.docx",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.rules_path_ctrl.SetValue(dlg.GetPath())

    def on_setup(self, event):
        nist_path = self.nist_path_ctrl.GetValue().strip()

        if not nist_path or not os.path.exists(nist_path):
            wx.MessageBox("Please select a valid NIST database file", "Error", wx.OK | wx.ICON_ERROR)
            return

        rules_path = self.rules_path_ctrl.GetValue().strip()
        if rules_path and not os.path.exists(rules_path):
            rules_path = None

        self.setup_btn.Enable(False)
        self.progress_ctrl.SetValue("Starting setup...\n")

        def progress_callback(msg):
            wx.CallAfter(self._append_progress, msg)

        def run_setup():
            try:
                self.assistant.setup_assistant(nist_path, rules_path, progress_callback)
                wx.CallAfter(self._setup_complete, True)
            except Exception as e:
                wx.CallAfter(self._append_progress, f"Error: {str(e)}")
                wx.CallAfter(self._setup_complete, False)

        thread = threading.Thread(target=run_setup)
        thread.daemon = True
        thread.start()

    def _append_progress(self, msg):
        self.progress_ctrl.AppendText(msg + "\n")

    def _setup_complete(self, success):
        self.setup_btn.Enable(True)
        self.setup_complete = success
        if success:
            self.delete_btn.Enable(True)
            wx.MessageBox("XPS Assistant setup complete!", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_delete(self, event):
        if wx.MessageBox("Delete the existing assistant? You'll need to set it up again.",
                         "Confirm Delete", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
            self.assistant.delete_assistant()
            self.progress_ctrl.SetValue("Assistant deleted.\n")
            self.delete_btn.Enable(False)
            self.setup_complete = False