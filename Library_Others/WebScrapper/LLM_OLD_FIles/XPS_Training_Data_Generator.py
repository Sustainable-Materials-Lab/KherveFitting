# XPS_Training_Data_Generator.py
# Generates fine-tuning training data from NIST_BE.xlsx
# Location: libraries/LLMs/XPS_Training_Data_Generator.py
#
# This creates training data in multiple formats:
# 1. JSONL for OpenAI/RunPod fine-tuning
# 2. Alpaca format for Llama fine-tuning
# 3. Conversation format for chat models

import pandas as pd
import json
import os
import random
from collections import defaultdict


class XPSTrainingDataGenerator:
    """
    Generate fine-tuning training data from NIST XPS database

    Creates diverse question-answer pairs covering:
    - Peak identification
    - Binding energy lookup
    - Fitting advice
    - Chemical state comparison
    - Doublet information
    """

    # Doublet information
    DOUBLETS = {
        '2p': {'ratio': '1:2', 'ratio_numeric': 0.5, 'levels': ('2p1/2', '2p3/2')},
        '3d': {'ratio': '2:3', 'ratio_numeric': 0.667, 'levels': ('3d3/2', '3d5/2')},
        '4f': {'ratio': '3:4', 'ratio_numeric': 0.75, 'levels': ('4f5/2', '4f7/2')},
        '3p': {'ratio': '1:2', 'ratio_numeric': 0.5, 'levels': ('3p1/2', '3p3/2')},
        '4d': {'ratio': '2:3', 'ratio_numeric': 0.667, 'levels': ('4d3/2', '4d5/2')},
    }

    # Common doublet separations (eV)
    DOUBLET_SEPARATIONS = {
        'Fe 2p': 13.1, 'Cu 2p': 19.8, 'Ni 2p': 17.3, 'Co 2p': 15.0,
        'Mn 2p': 11.1, 'Cr 2p': 9.2, 'Ti 2p': 5.7, 'Zn 2p': 23.0,
        'V 2p': 7.5, 'Sc 2p': 4.8, 'Ca 2p': 3.5,
        'Ag 3d': 6.0, 'Pd 3d': 5.3, 'Cd 3d': 6.7, 'In 3d': 7.5,
        'Au 4f': 3.7, 'Pt 4f': 3.3, 'Ir 4f': 3.0, 'W 4f': 2.2,
        'S 2p': 1.16, 'P 2p': 0.87, 'Si 2p': 0.6, 'Cl 2p': 1.6,
        'Mo 3d': 3.1, 'Nb 3d': 2.7, 'Zr 3d': 2.4,
    }

    # Fitting rules
    FITTING_RULES = {
        'Fe 2p': "Multiplet splitting required for Fe2+ and Fe3+. Use shake-up satellites. Fe metal requires asymmetric peak shape.",
        'Cu 2p': "Cu metal and Cu+ have no satellites. Cu2+ has strong shake-up satellite at ~942 eV. Use Auger parameter for Cu+/Cu0 distinction.",
        'Ni 2p': "Complex multiplet structure. Multiple satellites required. Asymmetric peaks for Ni metal.",
        'Ti 2p': "Clean doublet for TiO2. Multiple oxidation states may overlap. Ti metal requires asymmetric shape.",
        'C 1s': "Adventitious carbon at 284.8 eV for calibration. Watch for differential charging. π-π* satellite for sp2 carbon.",
        'O 1s': "Metal oxide ~530 eV, hydroxide ~531.5 eV, water ~533 eV. Often overlapping components.",
        'N 1s': "Wide chemical shift range. Nitride ~397 eV, amine ~399 eV, nitrate ~407 eV.",
        'Si 2p': "Small doublet (0.6 eV). Often fit as single peak. SiO2 at 103.5 eV.",
        'Al 2p': "Small doublet. Al metal at 72.8 eV, Al2O3 at 74.5 eV.",
        'S 2p': "1.16 eV doublet. Sulfide ~162 eV, sulfate ~169 eV.",
        'Zn 2p': "Large doublet (23 eV). Difficult to distinguish Zn, ZnO, Zn(OH)2 from 2p alone.",
        'Ag 3d': "Sharp peaks. Use Auger parameter for chemical state.",
        'Au 4f': "Reference standard at 84.0 eV. Very sharp peaks.",
    }

    def __init__(self, nist_file_path):
        """
        Initialize with NIST database

        Args:
            nist_file_path: Path to NIST_BE.xlsx
        """
        self.nist_path = nist_file_path
        self.df = None
        self.training_data = []

    def load_data(self):
        """Load NIST database"""
        print(f"Loading {self.nist_path}...")
        self.df = pd.read_excel(self.nist_path)
        print(f"Loaded {len(self.df)} entries")

        # Standardize column names
        column_mapping = {
            'BE (eV)': 'binding_energy',
            'Element': 'element',
            'Line': 'line',
            'Formula': 'formula',
            'Name': 'compound_name',
            'FWHM': 'fwhm',
            'Quality': 'quality'
        }

        for old_name, new_name in column_mapping.items():
            if old_name in self.df.columns:
                self.df[new_name] = self.df[old_name]

        # Clean data
        self.df = self.df.dropna(subset=['binding_energy', 'element', 'line'])
        self.df['binding_energy'] = pd.to_numeric(self.df['binding_energy'], errors='coerce')
        self.df = self.df.dropna(subset=['binding_energy'])

        print(f"After cleaning: {len(self.df)} entries")
        return self.df

    def generate_all_training_data(self, max_samples_per_type=5000):
        """Generate all types of training data"""
        if self.df is None:
            self.load_data()

        print("\nGenerating training data...")

        # 1. Peak identification questions
        self._generate_peak_identification(max_samples_per_type)

        # 2. Binding energy lookup questions
        self._generate_be_lookup(max_samples_per_type)

        # 3. Chemical state comparison
        self._generate_chemical_comparison(max_samples_per_type // 2)

        # 4. Fitting advice questions
        self._generate_fitting_advice(500)

        # 5. Doublet information
        self._generate_doublet_questions(500)

        # 6. Reference and quality questions
        self._generate_reference_questions(max_samples_per_type // 2)

        # 7. General XPS knowledge
        self._generate_general_knowledge(500)

        # Shuffle
        random.shuffle(self.training_data)

        print(f"\nTotal training samples: {len(self.training_data)}")
        return self.training_data

    def _generate_peak_identification(self, max_samples):
        """Generate peak identification Q&A pairs"""
        print("  Generating peak identification questions...")

        # Group by element and line
        grouped = self.df.groupby(['element', 'line'])

        count = 0
        for (element, line), group in grouped:
            if count >= max_samples:
                break

            for _, row in group.iterrows():
                if count >= max_samples:
                    break

                be = row['binding_energy']
                formula = row.get('formula', '')
                name = row.get('compound_name', '')
                fwhm = row.get('fwhm', '')
                quality = row.get('quality', '')
                author = row.get('Author', row.get('author', ''))
                journal = row.get('Journal', row.get('journal', row.get('Reference', '')))

                if pd.isna(formula) or not formula:
                    continue

                # Question variations
                questions = [
                    f"What is the chemical state for {element} {line} at {be:.2f} eV?",
                    f"Identify the peak at {be:.2f} eV in {element} {line}.",
                    f"What compound has {element} {line} binding energy of {be:.2f} eV?",
                    f"I have a peak at {be:.2f} eV in my {element} {line} spectrum. What is it?",
                ]

                # Build answer
                answer = f"The binding energy of {be:.2f} eV in {element} {line} corresponds to **{formula}**"
                if name and not pd.isna(name):
                    answer += f" ({name})"
                answer += "."

                # Add FWHM if available
                if fwhm and not pd.isna(fwhm) and fwhm > 0:
                    answer += f" Expected FWHM: {fwhm:.2f} eV."

                # Add quality and reference
                if quality and not pd.isna(quality):
                    answer += f" Data quality: {quality}."

                if author and not pd.isna(author):
                    ref_str = str(author)
                    if journal and not pd.isna(journal):
                        ref_str += f", {journal}"
                    answer += f" Reference: {ref_str}."

                # Add doublet info if applicable
                orbital_type = self._get_orbital_type(line)
                if orbital_type in self.DOUBLETS:
                    sep_key = f"{element} {orbital_type}"
                    if sep_key in self.DOUBLET_SEPARATIONS:
                        sep = self.DOUBLET_SEPARATIONS[sep_key]
                        ratio = self.DOUBLETS[orbital_type]['ratio']
                        answer += f" Doublet separation: {sep:.1f} eV, area ratio: {ratio}."

                # Add training sample
                question = random.choice(questions)
                self.training_data.append({
                    'instruction': question,
                    'output': answer,
                    'element': element,
                    'line': line,
                    'type': 'identification'
                })
                count += 1

        print(f"    Generated {count} peak identification samples")

    def _generate_be_lookup(self, max_samples):
        """Generate binding energy lookup questions"""
        print("  Generating binding energy lookup questions...")

        count = 0
        for _, row in self.df.iterrows():
            if count >= max_samples:
                break

            element = row['element']
            line = row['line']
            be = row['binding_energy']
            formula = row.get('formula', '')
            name = row.get('compound_name', '')
            quality = row.get('quality', '')
            author = row.get('Author', row.get('author', ''))
            journal = row.get('Journal', row.get('journal', row.get('Reference', '')))

            if pd.isna(formula) or not formula:
                continue

            # Question variations
            compound_desc = formula
            if name and not pd.isna(name):
                compound_desc = f"{formula} ({name})"

            questions = [
                f"What is the binding energy of {compound_desc} in {element} {line}?",
                f"What BE should I expect for {formula} in {element} {line}?",
                f"Where does {formula} appear in the {element} {line} spectrum?",
            ]

            answer = f"The binding energy of {compound_desc} in {element} {line} is **{be:.2f} eV**."

            # Add quality and reference
            if quality and not pd.isna(quality):
                answer += f" Data quality: {quality}."

            if author and not pd.isna(author):
                ref_str = str(author)
                if journal and not pd.isna(journal):
                    ref_str += f", {journal}"
                answer += f" Reference: {ref_str}."

            question = random.choice(questions)
            self.training_data.append({
                'instruction': question,
                'output': answer,
                'element': element,
                'line': line,
                'type': 'lookup'
            })
            count += 1

        print(f"    Generated {count} binding energy lookup samples")

    def _generate_chemical_comparison(self, max_samples):
        """Generate chemical state comparison questions"""
        print("  Generating chemical comparison questions...")

        # Group by element and line
        grouped = self.df.groupby(['element', 'line'])

        count = 0
        for (element, line), group in grouped:
            if count >= max_samples:
                break

            if len(group) < 2:
                continue

            # Get unique compounds
            compounds = group[['formula', 'binding_energy', 'compound_name']].drop_duplicates()
            compounds = compounds.dropna(subset=['formula'])

            if len(compounds) < 2:
                continue

            # Sample pairs
            compounds_list = compounds.to_dict('records')
            for i in range(min(3, len(compounds_list) - 1)):
                if count >= max_samples:
                    break

                c1 = compounds_list[i]
                c2 = compounds_list[i + 1]

                be_diff = abs(c1['binding_energy'] - c2['binding_energy'])

                question = f"What is the difference between {c1['formula']} and {c2['formula']} in {element} {line}?"

                answer = f"In {element} {line}:\n"
                answer += f"- {c1['formula']}: {c1['binding_energy']:.2f} eV\n"
                answer += f"- {c2['formula']}: {c2['binding_energy']:.2f} eV\n"
                answer += f"The chemical shift between them is {be_diff:.2f} eV."

                self.training_data.append({
                    'instruction': question,
                    'output': answer,
                    'element': element,
                    'line': line,
                    'type': 'comparison'
                })
                count += 1

        print(f"    Generated {count} chemical comparison samples")

    def _generate_fitting_advice(self, max_samples):
        """Generate fitting advice questions"""
        print("  Generating fitting advice questions...")

        count = 0
        for core_level, advice in self.FITTING_RULES.items():
            if count >= max_samples:
                break

            element = core_level.split()[0]
            orbital = core_level.split()[1]

            # Get doublet info
            doublet_info = ""
            if core_level in self.DOUBLET_SEPARATIONS:
                sep = self.DOUBLET_SEPARATIONS[core_level]
                orbital_type = self._get_orbital_type(orbital)
                if orbital_type in self.DOUBLETS:
                    ratio = self.DOUBLETS[orbital_type]['ratio']
                    doublet_info = f"Doublet separation: {sep:.1f} eV, area ratio: {ratio}."

            questions = [
                f"How should I fit {core_level}?",
                f"What are the fitting parameters for {core_level}?",
                f"Give me fitting advice for {element} {orbital}.",
                f"What constraints should I use for {core_level}?",
            ]

            answer = f"Fitting advice for {core_level}:\n\n"
            answer += advice + "\n"
            if doublet_info:
                answer += f"\n{doublet_info}\n"
            answer += "\nRecommended FWHM: 0.8-2.5 eV depending on spectrometer resolution."
            answer += "\nBackground: Shirley for most cases, Tougaard for quantitative analysis."

            for q in questions:
                self.training_data.append({
                    'instruction': q,
                    'output': answer,
                    'element': element,
                    'line': orbital,
                    'type': 'fitting_advice'
                })
                count += 1

        print(f"    Generated {count} fitting advice samples")

    def _generate_doublet_questions(self, max_samples):
        """Generate doublet information questions"""
        print("  Generating doublet questions...")

        count = 0
        for core_level, sep in self.DOUBLET_SEPARATIONS.items():
            if count >= max_samples:
                break

            element = core_level.split()[0]
            orbital = core_level.split()[1]
            orbital_type = self._get_orbital_type(orbital)

            if orbital_type not in self.DOUBLETS:
                continue

            ratio = self.DOUBLETS[orbital_type]['ratio']
            levels = self.DOUBLETS[orbital_type]['levels']

            questions = [
                f"What is the doublet separation for {core_level}?",
                f"What is the spin-orbit splitting for {element} {orbital}?",
                f"What ratio should I use for {core_level} doublet?",
            ]

            answer = f"For {core_level}:\n"
            answer += f"- Spin-orbit splitting: {sep:.1f} eV\n"
            answer += f"- Area ratio ({levels[0]}:{levels[1]}): {ratio}\n"
            answer += f"- The {levels[1]} peak appears at lower binding energy and is more intense."

            for q in questions:
                self.training_data.append({
                    'instruction': q,
                    'output': answer,
                    'element': element,
                    'line': orbital,
                    'type': 'doublet'
                })
                count += 1

        print(f"    Generated {count} doublet samples")

    def _generate_general_knowledge(self, max_samples):
        """Generate general XPS knowledge questions"""
        print("  Generating general knowledge questions...")

        general_qa = [
            {
                'instruction': "What is the calibration standard for XPS?",
                'output': "Common XPS calibration standards:\n- Au 4f7/2: 84.00 eV (most reliable)\n- Ag 3d5/2: 368.20 eV\n- Cu 2p3/2: 932.60 eV\n- C 1s (adventitious): 284.80 eV (convenient but less accurate)"
            },
            {
                'instruction': "What FWHM is typical for XPS peaks?",
                'output': "Typical FWHM ranges:\n- High-resolution monochromated Al Kα: 0.5-1.0 eV\n- Standard Al Kα: 0.8-1.5 eV\n- Mg Kα: 0.8-1.5 eV\n- Polymers and insulators: 1.0-2.5 eV (due to differential charging)\nFWHM should be consistent for peaks from the same chemical environment."
            },
            {
                'instruction': "What background should I use for XPS fitting?",
                'output': "XPS background types:\n- **Shirley**: Most common, good for most core levels. Iterative algorithm.\n- **Tougaard**: Better for quantitative analysis, physically meaningful.\n- **Linear**: Only for survey scans or very wide regions.\n- **Smart**: Combination approaches.\n\nRule: Background should never cut through the data."
            },
            {
                'instruction': "How do I identify shake-up satellites?",
                'output': "Shake-up satellites:\n- Appear at HIGHER binding energy than main peak (typically 5-10 eV higher)\n- Common in Cu2+, Ni2+, Co2+, and π-systems (aromatic compounds)\n- Intensity varies: strong in Cu2+ (~40% of main), weak in some systems\n- Absence of satellites can be diagnostic (Cu metal/Cu+ have no satellites)"
            },
            {
                'instruction': "When should I use asymmetric peak shapes?",
                'output': "Asymmetric peak shapes are required for:\n- Metallic samples (conduction electrons cause asymmetry)\n- Graphitic carbon (sp2)\n- Some conducting oxides\n\nUse Doniach-Sunjic (DS) or Lorentzian-Asymmetric (LA/LF) line shapes.\nAsymmetry tail extends to HIGHER binding energy."
            },
            {
                'instruction': "How do I use the Auger parameter?",
                'output': "Auger parameter (α) = KE(Auger) + BE(photoelectron)\n\nUseful for distinguishing:\n- Cu metal vs Cu2O (both Cu 2p3/2 ~ 932.5 eV)\n- Zn metal vs ZnO\n- Different Al compounds\n\nAdvantage: Independent of charging/calibration errors."
            },
            {
                'instruction': "What causes differential charging in XPS?",
                'output': "Differential charging occurs when:\n- Sample is insulating\n- Different regions charge to different potentials\n- Results in: broadened peaks, shifted binding energies, asymmetric peak shapes\n\nSolutions:\n- Use charge neutralizer (flood gun)\n- Apply conductive coating\n- Use internal reference (adventitious C 1s)"
            },
        ]

        for qa in general_qa[:max_samples]:
            qa['type'] = 'general'
            qa['element'] = ''
            qa['line'] = ''
            self.training_data.append(qa)

        print(f"    Generated {len(general_qa)} general knowledge samples")

    def _generate_reference_questions(self, max_samples):
        """Generate questions about references and data quality"""
        print("  Generating reference questions...")

        count = 0
        # Group by quality
        if 'quality' in self.df.columns:
            good_data = self.df[self.df['quality'].str.contains('Good', case=False, na=False)]

            for _, row in good_data.iterrows():
                if count >= max_samples:
                    break

                element = row['element']
                line = row['line']
                be = row['binding_energy']
                formula = row.get('formula', '')
                author = row.get('Author', row.get('author', ''))
                journal = row.get('Journal', row.get('journal', row.get('Reference', '')))

                if pd.isna(formula) or not formula:
                    continue
                if pd.isna(author) or not author:
                    continue

                questions = [
                    f"What is the most reliable binding energy for {formula} in {element} {line}?",
                    f"Give me a high-quality reference for {formula} binding energy.",
                    f"What is the reference for {formula} at {be:.2f} eV?",
                ]

                answer = f"For {formula} in {element} {line}, a high-quality measurement gives **{be:.2f} eV**."

                ref_str = str(author)
                if journal and not pd.isna(journal):
                    ref_str += f", {journal}"
                answer += f" Reference: {ref_str} (Quality: Good)."

                self.training_data.append({
                    'instruction': random.choice(questions),
                    'output': answer,
                    'element': element,
                    'line': line,
                    'type': 'reference'
                })
                count += 1

        print(f"    Generated {count} reference samples")

    def _get_orbital_type(self, line):
        """Extract orbital type from line (e.g., '2p3/2' -> '2p')"""
        import re
        match = re.match(r'(\d[spdf])', str(line))
        if match:
            return match.group(1)
        return ''

    def save_jsonl(self, output_path, format_type='openai'):
        """
        Save training data in JSONL format

        Args:
            output_path: Output file path
            format_type: 'openai', 'alpaca', or 'conversation'
        """
        print(f"\nSaving to {output_path} (format: {format_type})...")

        with open(output_path, 'w', encoding='utf-8') as f:
            for item in self.training_data:
                if format_type == 'openai':
                    # OpenAI fine-tuning format
                    entry = {
                        "messages": [
                            {"role": "system", "content": "You are an expert XPS analyst assistant."},
                            {"role": "user", "content": item['instruction']},
                            {"role": "assistant", "content": item['output']}
                        ]
                    }
                elif format_type == 'alpaca':
                    # Alpaca/Llama format
                    entry = {
                        "instruction": item['instruction'],
                        "input": "",
                        "output": item['output']
                    }
                elif format_type == 'conversation':
                    # Conversation format for vLLM/RunPod
                    entry = {
                        "prompt": f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\nYou are an expert XPS analyst.\n<|eot_id|><|start_header_id|>user<|end_header_id|>\n{item['instruction']}\n<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n",
                        "completion": item['output']
                    }
                else:
                    entry = item

                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        print(f"Saved {len(self.training_data)} samples")

    def save_train_val_split(self, output_dir, val_ratio=0.1, format_type='openai'):
        """Save with train/validation split"""
        os.makedirs(output_dir, exist_ok=True)

        # Shuffle
        data = self.training_data.copy()
        random.shuffle(data)

        # Split
        val_size = int(len(data) * val_ratio)
        val_data = data[:val_size]
        train_data = data[val_size:]

        # Save
        self.training_data = train_data
        self.save_jsonl(os.path.join(output_dir, 'train.jsonl'), format_type)

        self.training_data = val_data
        self.save_jsonl(os.path.join(output_dir, 'val.jsonl'), format_type)

        self.training_data = data  # Restore

        print(f"\nTrain: {len(train_data)}, Validation: {len(val_data)}")

    def get_statistics(self):
        """Get statistics about generated data"""
        if not self.training_data:
            return {}

        stats = {
            'total': len(self.training_data),
            'by_type': defaultdict(int),
            'by_element': defaultdict(int),
        }

        for item in self.training_data:
            stats['by_type'][item.get('type', 'unknown')] += 1
            if item.get('element'):
                stats['by_element'][item['element']] += 1

        return stats


def main():
    """Main function to generate training data"""
    import argparse

    parser = argparse.ArgumentParser(description='Generate XPS fine-tuning training data')
    parser.add_argument('--nist', required=True, help='Path to NIST_BE.xlsx')
    parser.add_argument('--output', default='xps_training_data', help='Output directory')
    parser.add_argument('--format', default='openai', choices=['openai', 'alpaca', 'conversation'],
                        help='Output format')
    parser.add_argument('--max-samples', type=int, default=10000, help='Max samples per type')

    args = parser.parse_args()

    # Generate
    generator = XPSTrainingDataGenerator(args.nist)
    generator.load_data()
    generator.generate_all_training_data(args.max_samples)

    # Save
    generator.save_train_val_split(args.output, format_type=args.format)

    # Print stats
    stats = generator.get_statistics()
    print("\n=== Statistics ===")
    print(f"Total samples: {stats['total']}")
    print("\nBy type:")
    for t, count in sorted(stats['by_type'].items()):
        print(f"  {t}: {count}")
    print(f"\nUnique elements: {len(stats['by_element'])}")


if __name__ == '__main__':
    main()