# XPS_RunPod.py - Connect to RunPod vLLM Endpoint
# Location: libraries/LLMs/XPS_RunPod.py

import requests
import json
import time
import os


class XPSRunPod:
    """
    Connect to your self-hosted XPS LLM on RunPod
    Uses vLLM serverless endpoint with Llama 3.1
    """

    CONFIG_PATH = os.path.expanduser("~/.khervefitting/runpod_config.json")

    # XPS System prompt - this makes the model an XPS expert
    SYSTEM_PROMPT = """You are an expert XPS (X-ray Photoelectron Spectroscopy) analyst assistant for KherveFitting software.

## Your Knowledge Base

### Calibration Standards
- Au 4f7/2: 84.00 eV
- Ag 3d5/2: 368.20 eV  
- Cu 2p3/2: 932.60 eV
- C 1s (adventitious): 284.80 eV

### Doublet Separations and Ratios
- 2p orbitals: ratio 1:2 (2p1/2:2p3/2)
- 3d orbitals: ratio 2:3 (3d3/2:3d5/2)
- 4f orbitals: ratio 3:4 (4f5/2:4f7/2)

Common separations:
- Fe 2p: 13.1 eV
- Cu 2p: 19.8 eV
- Ni 2p: 17.3 eV
- Co 2p: 15.0 eV
- Mn 2p: 11.1 eV
- Cr 2p: 9.2 eV
- Ti 2p: 5.7 eV
- Zn 2p: 23.0 eV
- Ag 3d: 6.0 eV
- Au 4f: 3.7 eV
- Pt 4f: 3.3 eV
- S 2p: 1.16 eV
- P 2p: 0.87 eV
- Si 2p: 0.6 eV
- Cl 2p: 1.6 eV

### Common Binding Energies

C 1s:
- C-C/C-H (adventitious): 284.8 eV
- C-O (alcohol, ether): 286.5 eV
- C=O (carbonyl): 287.8-288.2 eV
- O-C=O (carboxyl): 289.0 eV
- CO3 (carbonate): 289.5 eV
- π-π* satellite: 291.5 eV
- CF2: 291.0 eV
- CF3: 293.0 eV

O 1s:
- Metal oxide (M-O): 529.5-530.5 eV
- Hydroxide (M-OH): 531.0-532.0 eV
- Organic C=O: 531.5-532.0 eV
- Organic C-O: 532.5-533.5 eV
- Adsorbed water: 533.0-534.0 eV

N 1s:
- Metal nitride: 397.0-398.0 eV
- Amine (C-NH2): 399.0-400.0 eV
- Amide (N-C=O): 400.0-400.5 eV
- Quaternary N: 401.5-402.5 eV
- Nitrate (NO3): 407.0 eV

Fe 2p3/2:
- Fe metal: 706.8 eV (asymmetric)
- FeO (Fe2+): 709.5 eV (with satellite at 715 eV)
- Fe2O3 (Fe3+): 710.9 eV (with satellite at 719 eV)
- Fe3O4: 710.5 eV (mixed Fe2+/Fe3+)
- FeOOH: 711.5 eV

Cu 2p3/2:
- Cu metal: 932.6 eV (no satellite)
- Cu2O (Cu+): 932.4 eV (no satellite)
- CuO (Cu2+): 933.6 eV (strong satellite at 942 eV)
- Cu(OH)2: 934.5 eV (satellite at 942 eV)

Ti 2p3/2:
- Ti metal: 454.0 eV (asymmetric)
- TiO (Ti2+): 455.0 eV
- Ti2O3 (Ti3+): 457.0 eV
- TiO2 (Ti4+): 458.8 eV

Ni 2p3/2:
- Ni metal: 852.7 eV
- NiO: 854.0 eV (complex satellites)
- Ni(OH)2: 855.8 eV
- NiOOH: 856.5 eV

Zn 2p3/2:
- Zn metal: 1021.8 eV
- ZnO: 1022.0 eV
- Zn(OH)2: 1022.5 eV

Si 2p:
- Si metal: 99.3 eV
- SiO2: 103.5 eV
- Si3N4: 101.8 eV

Al 2p:
- Al metal: 72.8 eV
- Al2O3: 74.5 eV

### Fitting Rules
1. FWHM should be consistent for peaks from same chemical environment (typically 0.8-2.5 eV)
2. Metallic peaks require asymmetric line shapes (Doniach-Sunjic or LF)
3. Shake-up satellites appear at higher BE than main peak
4. Background should never cut through data
5. Shirley background for most core levels
6. Tougaard background for quantitative analysis
7. Linear background only for survey scans
8. Avoid adding peaks without physical justification
9. Chi-squared < 3 is acceptable, < 1 may indicate overfitting

### Response Format
Always provide:
1. Most likely chemical assignment with BE (format: X.XX eV)
2. Alternative possibilities
3. Expected FWHM range
4. Relevant satellites or special features
5. Fitting constraints (doublet separation, ratio)
"""

    def __init__(self, api_key=None, endpoint_id=None):
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.base_url = None

        if endpoint_id:
            self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

        # Load saved config
        self._load_config()

    def _load_config(self):
        """Load saved configuration"""
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    if not self.api_key:
                        self.api_key = config.get('api_key')
                    if not self.endpoint_id:
                        self.endpoint_id = config.get('endpoint_id')
                        if self.endpoint_id:
                            self.base_url = f"https://api.runpod.ai/v2/{self.endpoint_id}"
            except:
                pass

    def save_config(self, api_key=None, endpoint_id=None):
        """Save configuration"""
        if api_key:
            self.api_key = api_key
        if endpoint_id:
            self.endpoint_id = endpoint_id
            self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

        config_dir = os.path.dirname(self.CONFIG_PATH)
        os.makedirs(config_dir, exist_ok=True)

        with open(self.CONFIG_PATH, 'w') as f:
            json.dump({
                'api_key': self.api_key,
                'endpoint_id': self.endpoint_id
            }, f)

    def is_ready(self):
        """Check if configured"""
        return bool(self.api_key and self.endpoint_id)

    def _build_prompt(self, user_message):
        """Build Llama 3.1 chat format prompt"""
        prompt = "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
        prompt += self.SYSTEM_PROMPT + "\n"
        prompt += "<|eot_id|><|start_header_id|>user<|end_header_id|>\n"
        prompt += user_message + "\n"
        prompt += "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
        return prompt

    def _query(self, user_message, max_tokens=1000):
        """Send query to RunPod endpoint"""
        if not self.is_ready():
            return "Error: RunPod not configured. Set API key and Endpoint ID in Config."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "input": {
                "prompt": self._build_prompt(user_message),
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "top_p": 0.9
            }
        }

        try:
            # Submit job
            response = requests.post(
                f"{self.base_url}/run",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                return f"Error: API returned {response.status_code} - {response.text}"

            result = response.json()
            job_id = result.get('id')

            if not job_id:
                # Synchronous response
                if 'output' in result:
                    return self._extract_response(result['output'])
                return f"Error: Unexpected response format"

            # Poll for result (async)
            return self._poll_for_result(job_id, headers)

        except requests.exceptions.Timeout:
            return "Error: Request timed out"
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to RunPod"
        except Exception as e:
            return f"Error: {str(e)}"

    def _poll_for_result(self, job_id, headers, max_wait=120):
        """Poll for async job result"""
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(
                    f"{self.base_url}/status/{job_id}",
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    result = response.json()
                    status = result.get('status')

                    if status == 'COMPLETED':
                        output = result.get('output')
                        return self._extract_response(output)
                    elif status == 'FAILED':
                        return f"Error: Job failed - {result.get('error', 'Unknown error')}"
                    elif status in ['IN_QUEUE', 'IN_PROGRESS']:
                        time.sleep(2)
                        continue
                    else:
                        time.sleep(2)
                        continue
                else:
                    time.sleep(2)

            except Exception as e:
                time.sleep(2)

        return "Error: Request timed out waiting for response"

    def _extract_response(self, output):
        """Extract text from vLLM output"""
        try:
            if isinstance(output, str):
                return output
            elif isinstance(output, list):
                # Format: [{'choices': [{'tokens': ['text']}]}]
                if output and isinstance(output[0], dict):
                    if 'choices' in output[0]:
                        choices = output[0]['choices']
                        if choices and isinstance(choices[0], dict):
                            tokens = choices[0].get('tokens', [])
                            if tokens:
                                return ''.join(tokens) if isinstance(tokens, list) else str(tokens)
                    if 'text' in output[0]:
                        return output[0]['text']
                return str(output)
            elif isinstance(output, dict):
                if 'choices' in output:
                    choices = output['choices']
                    if choices and isinstance(choices[0], dict):
                        tokens = choices[0].get('tokens', [])
                        if tokens:
                            return ''.join(tokens) if isinstance(tokens, list) else str(tokens)
                        return choices[0].get('text', str(output))
                if 'text' in output:
                    return output['text']
                return str(output)
            return str(output)
        except Exception as e:
            return str(output)

    # ==================== XPS Query Methods ====================

    def identify_peak(self, element, orbital, binding_energy):
        """Identify a peak"""
        message = f"""Identify the chemical state for:
- Element: {element}
- Orbital: {orbital}
- Binding Energy: {binding_energy:.2f} eV

Provide:
1. Most likely chemical assignment with confidence
2. Alternative possibilities within ±1 eV
3. Expected FWHM range
4. Any satellites or special features to look for
5. Doublet constraints if applicable"""

        return self._query(message)

    def analyze_spectrum(self, core_level, peaks, sample_info=None, spectrum_summary=None):
        """Analyze spectrum with fitted peaks"""
        message = f"Analyze this {core_level} spectrum:\n\n"

        if spectrum_summary:
            message += f"{spectrum_summary}\n\n"

        if peaks:
            message += "Fitted peaks:\n"
            for i, peak in enumerate(peaks, 1):
                message += f"- Peak {i} ({peak.get('name', '')}): {peak['position']:.2f} eV"
                message += f", FWHM: {peak['fwhm']:.2f} eV"
                if peak.get('area'):
                    message += f", Area: {peak['area']:.2f}"
                if peak.get('l_g'):
                    message += f", L/G: {peak['l_g']:.2f}%"
                message += "\n"
        else:
            message += "No peaks fitted yet.\n"

        if sample_info:
            message += f"\nSample information: {sample_info}\n"

        message += """
Provide:
1. Chemical state assignment for each peak
2. Assessment of FWHM values (reasonable?)
3. Missing components to consider
4. Suggestions for improving the fit"""

        return self._query(message)

    def get_fitting_advice(self, element, orbital):
        """Get fitting advice for a core level"""
        message = f"""Provide detailed fitting recommendations for {element} {orbital}:

1. Doublet separation (eV) and area ratio
2. Recommended FWHM range
3. Peak shape (symmetric GL, asymmetric LA/LF)
4. Background type (Shirley, Tougaard, Linear)
5. Common chemical states with their binding energies
6. Satellites to include (shake-up, plasmons)
7. Common fitting mistakes to avoid"""

        return self._query(message)

    def suggest_peak_fitting(self, core_level, spectrum_summary, sample_info=None):
        """Suggest peak fitting parameters"""
        message = f"""Suggest peak fitting for this {core_level} spectrum:

{spectrum_summary}
"""
        if sample_info:
            message += f"\nSample: {sample_info}\n"

        message += """
For each peak you recommend, provide in this exact format:
Peak 1: [position] eV, FWHM: [width] eV - [chemical assignment]
Peak 2: [position] eV, FWHM: [width] eV - [chemical assignment]
(continue for all peaks)

Consider:
- Doublet peaks with correct separation and ratio
- Satellite peaks if needed
- Reasonable FWHM values
- Background type recommendation"""

        return self._query(message)

    def ask(self, question):
        """Ask any XPS question"""
        return self._query(question)

    def ask_question(self, question, element=None, orbital=None):
        """Ask question with optional element/orbital context"""
        if element and orbital:
            message = f"Regarding {element} {orbital}:\n\n{question}"
        else:
            message = question
        return self._query(message)

    def test_connection(self):
        """Test connection to endpoint"""
        if not self.is_ready():
            return False, "Not configured"

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(
                f"{self.base_url}/health",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                return True, "Connected"
            else:
                return False, f"Status {response.status_code}"
        except Exception as e:
            return False, str(e)