# XPS_Assistant.py - OpenAI Assistants API (compatible with v2.15.0)
# Location: libraries/LLMs/XPS_Assistant.py
#
# This creates a SPECIALIZED AGENT that has access to your XPS database

import os
import json
import time
from openai import OpenAI


class XPSAssistant:
    """
    Specialized XPS Agent using OpenAI Assistants API

    Compatible with OpenAI Python library v2.x
    Uses file attachments on messages instead of vector stores
    """

    CONFIG_PATH = os.path.expanduser("~/.khervefitting/xps_assistant_config.json")

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.client = None
        self.assistant_id = None
        self.file_id = None
        self.thread_id = None

        if api_key:
            self._init_client()
            self._load_config()

    def set_api_key(self, api_key):
        """Set API key and initialize client"""
        self.api_key = api_key
        self._init_client()
        self._load_config()

    def _init_client(self):
        """Initialize OpenAI client"""
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def _load_config(self):
        """Load saved assistant configuration"""
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    self.assistant_id = config.get('assistant_id')
                    self.file_id = config.get('file_id')
                    print(f"Loaded existing assistant: {self.assistant_id}")
            except:
                pass

    def _save_config(self):
        """Save assistant configuration"""
        config_dir = os.path.dirname(self.CONFIG_PATH)
        os.makedirs(config_dir, exist_ok=True)

        with open(self.CONFIG_PATH, 'w') as f:
            json.dump({
                'assistant_id': self.assistant_id,
                'file_id': self.file_id
            }, f)

    def setup_assistant(self, nist_file_path, rules_file_path=None, progress_callback=None):
        """
        Set up the XPS Assistant with your knowledge files
        """
        if not self.client:
            raise ValueError("API key not set")

        def report(msg):
            print(msg)
            if progress_callback:
                progress_callback(msg)

        try:
            # Step 1: Upload file for assistants
            report(f"Uploading {os.path.basename(nist_file_path)}...")

            with open(nist_file_path, 'rb') as f:
                file = self.client.files.create(
                    file=f,
                    purpose="assistants"
                )

            self.file_id = file.id
            report(f"Uploaded: {os.path.basename(nist_file_path)} (ID: {self.file_id})")

            # Step 2: Create the Assistant with code interpreter (can read files)
            report("Creating XPS Assistant...")

            instructions = """You are an expert XPS (X-ray Photoelectron Spectroscopy) analyst assistant for KherveFitting software.

## Your Knowledge
You have access to the NIST XPS Database file with ~56,000 binding energy entries.
The file contains columns: Element, Line, BE (eV), Formula, Name, Author, Journal, Quality, FWHM, etc.

## IMPORTANT: Always search the file
When asked about binding energies, compounds, or elements:
1. Use code interpreter to read and search the uploaded file
2. Filter by Element and Line (orbital) columns
3. Report the BE (eV) values you find

## Your Capabilities
1. **Peak Identification**: Search the database for binding energies matching user queries
2. **Fitting Advice**: Recommend peak shapes, FWHM, constraints based on data
3. **Database Queries**: List compounds, count entries, find specific data

## Rules
- ALWAYS use code interpreter to search the file - don't guess
- Cite specific binding energies with .2f precision (e.g., 284.80 eV)
- When multiple matches exist, show the most common/reliable ones
- Note the Formula and Name columns for compound identification"""

            assistant = self.client.beta.assistants.create(
                name="XPS Fitting Expert",
                instructions=instructions,
                model="gpt-4o",
                tools=[{"type": "code_interpreter"}]
            )

            self.assistant_id = assistant.id
            self._save_config()

            report(f"Assistant created: {self.assistant_id}")
            report("Setup complete!")

            return True

        except Exception as e:
            report(f"Error: {str(e)}")
            raise

    def is_ready(self):
        """Check if assistant is set up and ready"""
        return self.client is not None and self.assistant_id is not None and self.file_id is not None

    def start_conversation(self):
        """Start a new conversation thread"""
        if not self.client:
            raise ValueError("API key not set")

        thread = self.client.beta.threads.create()
        self.thread_id = thread.id
        return self.thread_id

    def ask(self, question, thread_id=None):
        """
        Ask a question to the XPS Assistant
        """
        if not self.is_ready():
            return "Error: Assistant not set up. Please run setup first."

        try:
            # Use existing thread or create new one
            if thread_id:
                self.thread_id = thread_id
            elif not self.thread_id:
                self.start_conversation()

            # Add message with file attachment
            self.client.beta.threads.messages.create(
                thread_id=self.thread_id,
                role="user",
                content=question,
                attachments=[
                    {
                        "file_id": self.file_id,
                        "tools": [{"type": "code_interpreter"}]
                    }
                ]
            )

            # Run the assistant
            run = self.client.beta.threads.runs.create(
                thread_id=self.thread_id,
                assistant_id=self.assistant_id
            )

            # Wait for completion
            while True:
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread_id,
                    run_id=run.id
                )

                if run.status == "completed":
                    break
                elif run.status in ["failed", "cancelled", "expired"]:
                    return f"Error: Run {run.status} - {run.last_error}"
                elif run.status == "requires_action":
                    # Handle tool calls if needed
                    pass

                time.sleep(1)

            # Get the response
            messages = self.client.beta.threads.messages.list(
                thread_id=self.thread_id,
                order="desc",
                limit=1
            )

            if messages.data:
                response = messages.data[0]
                text_parts = []
                for content in response.content:
                    if content.type == "text":
                        text_parts.append(content.text.value)

                return "\n".join(text_parts)

            return "No response received"

        except Exception as e:
            return f"Error: {str(e)}"

    def identify_peak(self, element, orbital, binding_energy):
        """Identify a peak"""
        question = f"""Search the NIST database file for {element} {orbital}.

Find entries near {binding_energy:.2f} eV (within ±1 eV).

Show me:
1. The closest matches with their Formula, Name, and exact BE
2. The most likely chemical assignment
3. Any other compounds at similar binding energies"""

        return self.ask(question)

    def analyze_spectrum(self, core_level, peaks, sample_info=None, spectrum_summary=None):
        """Analyze fitted peaks"""
        question = f"Analyze this {core_level} spectrum.\n\n"

        if spectrum_summary:
            question += f"{spectrum_summary}\n\n"

        if peaks:
            question += "Fitted peaks:\n"
            for i, peak in enumerate(peaks, 1):
                question += f"- Peak {i}: {peak['position']:.2f} eV, FWHM: {peak['fwhm']:.2f} eV"
                if peak.get('area'):
                    question += f", Area: {peak['area']:.2f}"
                question += "\n"

        if sample_info:
            question += f"\nSample: {sample_info}\n"

        question += "\nSearch the database file and identify the chemical states for each peak."

        return self.ask(question)

    def get_fitting_advice(self, element, orbital):
        """Get fitting advice for a core level"""
        question = f"""Search the database file for all {element} {orbital} entries.

Tell me:
1. How many entries are there?
2. What is the BE range (min to max)?
3. List the unique compounds/formulas found
4. What are the most common binding energies?
5. Recommend fitting parameters based on this data"""

        return self.ask(question)

    def search_database(self, query):
        """Search the database"""
        question = f"""Search the XPS database file for: {query}

List all matching entries with their Element, Line, BE (eV), Formula, and Name."""

        return self.ask(question)

    def get_database_stats(self, element=None, orbital=None):
        """Get database statistics"""
        if element and orbital:
            question = f"Count the number of entries in the database for {element} {orbital}. Also list all unique formulas/compounds."
        elif element:
            question = f"Count entries for element {element}. List all available orbitals/lines for this element."
        else:
            question = "Give me statistics about the database: total entries, number of unique elements, and list all elements."

        return self.ask(question)

    def delete_assistant(self):
        """Delete the assistant (cleanup)"""
        if not self.client:
            return

        try:
            if self.assistant_id:
                self.client.beta.assistants.delete(self.assistant_id)
                print(f"Deleted assistant: {self.assistant_id}")

            if self.file_id:
                self.client.files.delete(self.file_id)
                print(f"Deleted file: {self.file_id}")

            if os.path.exists(self.CONFIG_PATH):
                os.remove(self.CONFIG_PATH)

            self.assistant_id = None
            self.file_id = None

        except Exception as e:
            print(f"Error during cleanup: {e}")