# XPS_Knowledge.py - XPS knowledge base using NIST database
# Location: libraries/LLMs/XPS_Knowledge.py

import sqlite3
import os
import pandas as pd


class XPSKnowledge:
    """
    XPS Knowledge Database
    - Loads NIST binding energies from Excel
    - Stores in SQLite for fast queries
    - Includes fitting rules from XPSFitting.com
    """

    def __init__(self):
        self.db_dir = os.path.expanduser("~/.khervefitting")
        os.makedirs(self.db_dir, exist_ok=True)
        self.db_path = os.path.join(self.db_dir, "xps_knowledge.db")
        self._init_database()

    def _init_database(self):
        """Initialize database, load NIST data if needed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nist_binding_energies'")
        if cursor.fetchone() is None:
            self._create_tables(cursor)
            self._load_nist_data(cursor)
            self._populate_fitting_rules(cursor)
            self._populate_doublets(cursor)
            conn.commit()
            print("XPS Knowledge database initialized")

        conn.close()

    def _create_tables(self, cursor):
        """Create database tables"""

        # NIST binding energies table
        cursor.execute("""
            CREATE TABLE nist_binding_energies (
                id INTEGER PRIMARY KEY,
                element TEXT NOT NULL,
                line TEXT NOT NULL,
                binding_energy REAL NOT NULL,
                formula TEXT,
                compound_name TEXT,
                author TEXT,
                journal TEXT,
                quality TEXT,
                energy_uncertainty REAL,
                energy_resolution REAL,
                fwhm REAL,
                gaussian_width REAL,
                lorentzian_width REAL,
                excitation_energy TEXT,
                calibration TEXT,
                charge_reference TEXT,
                specimen TEXT,
                notes TEXT
            )
        """)

        # Fitting rules table
        cursor.execute("""
            CREATE TABLE fitting_rules (
                id INTEGER PRIMARY KEY,
                element TEXT,
                orbital TEXT,
                rule_type TEXT NOT NULL,
                rule TEXT NOT NULL,
                source TEXT
            )
        """)

        # Doublet information table
        cursor.execute("""
            CREATE TABLE doublets (
                id INTEGER PRIMARY KEY,
                element TEXT NOT NULL,
                orbital TEXT NOT NULL,
                separation REAL NOT NULL,
                ratio TEXT NOT NULL,
                notes TEXT
            )
        """)

        # Create indexes for fast queries
        cursor.execute("CREATE INDEX idx_nist_element ON nist_binding_energies(element)")
        cursor.execute("CREATE INDEX idx_nist_line ON nist_binding_energies(line)")
        cursor.execute("CREATE INDEX idx_nist_be ON nist_binding_energies(binding_energy)")
        cursor.execute("CREATE INDEX idx_rules_element ON fitting_rules(element)")

    def _load_nist_data(self, cursor):
        """Load NIST data from Excel file"""

        # Find the NIST Excel file
        possible_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'NIST_BE.xlsx'),
            os.path.join(os.path.dirname(__file__), '..', '..', 'NIST_BE.parquet'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'NIST_BE.xlsx'),
            "NIST_BE.xlsx",
        ]

        nist_path = None
        for path in possible_paths:
            if os.path.exists(path):
                nist_path = path
                break

        if nist_path is None:
            print("Warning: NIST_BE.xlsx not found. Using minimal built-in data.")
            self._populate_minimal_data(cursor)
            return

        print(f"Loading NIST data from: {nist_path}")

        # Load Excel file
        if nist_path.endswith('.parquet'):
            df = pd.read_parquet(nist_path)
        else:
            df = pd.read_excel(nist_path)

        # Insert data into SQLite
        count = 0
        for _, row in df.iterrows():
            try:
                cursor.execute("""
                    INSERT INTO nist_binding_energies 
                    (element, line, binding_energy, formula, compound_name, author, journal,
                     quality, energy_uncertainty, energy_resolution, fwhm, gaussian_width,
                     lorentzian_width, excitation_energy, calibration, charge_reference,
                     specimen, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(row.get('Element', '')),
                    str(row.get('Line', '')),
                    float(row.get('BE (eV)', 0)) if pd.notna(row.get('BE (eV)')) else 0,
                    str(row.get('Formula', '')) if pd.notna(row.get('Formula')) else '',
                    str(row.get('Name', '')) if pd.notna(row.get('Name')) else '',
                    str(row.get('Author', '')) if pd.notna(row.get('Author')) else '',
                    str(row.get('Journal', '')) if pd.notna(row.get('Journal')) else '',
                    str(row.get('Quality', '')) if pd.notna(row.get('Quality')) else '',
                    float(row.get('Energy Uncertainty', 0)) if pd.notna(row.get('Energy Uncertainty')) else None,
                    float(row.get('Overal Energy Resolution (eV)', 0)) if pd.notna(row.get('Overal Energy Resolution (eV)')) else None,
                    float(row.get('Full Width at Half-maximum Intensity (eV)', 0)) if pd.notna(row.get('Full Width at Half-maximum Intensity (eV)')) else None,
                    float(row.get('Gaussian Width (eV)', 0)) if pd.notna(row.get('Gaussian Width (eV)')) else None,
                    float(row.get('Lorentzian Width (eV)', 0)) if pd.notna(row.get('Lorentzian Width (eV)')) else None,
                    str(row.get('Excitation Energy', '')) if pd.notna(row.get('Excitation Energy')) else '',
                    str(row.get('Calibration', '')) if pd.notna(row.get('Calibration')) else '',
                    str(row.get('Charge Reference', '')) if pd.notna(row.get('Charge Reference')) else '',
                    str(row.get('Specimen', '')) if pd.notna(row.get('Specimen')) else '',
                    str(row.get('Notes', '')) if pd.notna(row.get('Notes')) else '',
                ))
                count += 1
            except Exception as e:
                print(f"Error inserting row: {e}")
                continue

        print(f"Loaded {count} NIST binding energy entries")

    def _populate_minimal_data(self, cursor):
        """Populate with minimal data if NIST file not found"""
        minimal_data = [
            ('C', '1s', 284.8, 'C', 'Adventitious Carbon', 'Reference'),
            ('C', '1s', 286.5, 'C-O', 'C-O bond', 'Reference'),
            ('C', '1s', 288.5, 'C=O', 'Carbonyl', 'Reference'),
            ('C', '1s', 289.0, 'O-C=O', 'Carboxyl', 'Reference'),
            ('O', '1s', 530.0, 'Metal-O', 'Metal oxide', 'Reference'),
            ('O', '1s', 531.5, 'OH', 'Hydroxide', 'Reference'),
            ('O', '1s', 533.0, 'H2O', 'Adsorbed water', 'Reference'),
            ('Au', '4f7/2', 84.0, 'Au', 'Gold metal', 'Reference'),
            ('Ag', '3d5/2', 368.2, 'Ag', 'Silver metal', 'Reference'),
            ('Cu', '2p3/2', 932.6, 'Cu', 'Copper metal', 'Reference'),
            ('Cu', '2p3/2', 933.6, 'CuO', 'Copper(II) oxide', 'Reference'),
            ('Fe', '2p3/2', 706.8, 'Fe', 'Iron metal', 'Reference'),
            ('Fe', '2p3/2', 710.9, 'Fe2O3', 'Iron(III) oxide', 'Reference'),
        ]

        for element, line, be, formula, name, source in minimal_data:
            cursor.execute("""
                INSERT INTO nist_binding_energies 
                (element, line, binding_energy, formula, compound_name, author)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (element, line, be, formula, name, source))

    def _populate_fitting_rules(self, cursor):
        """Populate fitting rules from XPSFitting.com and general knowledge"""
        rules = [
            # General rules
            (None, None, 'general', 'Doublet peaks must maintain fixed separation based on spin-orbit coupling', 'XPSFitting.com'),
            (None, None, 'general', 'Area ratios for doublets are determined by degeneracy (2j+1)', 'XPSFitting.com'),
            (None, None, 'general', 'FWHM should be consistent for peaks from the same chemical environment', 'XPSFitting.com'),
            (None, None, 'general', 'Metallic peaks often require asymmetric line shapes (Doniach-Sunjic)', 'XPSFitting.com'),
            (None, None, 'general', 'Shake-up satellites appear at higher binding energy than main peak', 'XPSFitting.com'),
            (None, None, 'general', 'Background should not cut through the data', 'General'),
            (None, None, 'general', 'Chi-squared values below 1 may indicate overfitting', 'General'),
            (None, None, 'general', 'Peak positions should match literature values within ±0.2 eV for calibrated spectra', 'XPSFitting.com'),
            (None, None, 'calibration', 'C 1s adventitious carbon is typically used at 284.8 eV for charge referencing', 'XPSFitting.com'),
            (None, None, 'calibration', 'Au 4f7/2 at 84.0 eV is the primary calibration standard', 'NIST'),
            (None, None, 'calibration', 'Ag 3d5/2 at 368.2 eV can be used as calibration standard', 'NIST'),
            (None, None, 'background', 'Shirley background is appropriate for most core levels', 'XPSFitting.com'),
            (None, None, 'background', 'Tougaard background is more physically meaningful but complex', 'XPSFitting.com'),
            (None, None, 'background', 'Linear background should only be used for wide survey scans', 'General'),
            (None, None, 'fwhm', 'Peak FWHM typically ranges from 0.8-2.5 eV depending on spectrometer resolution', 'XPSFitting.com'),
            (None, None, 'fwhm', 'Monochromated Al Ka typically gives FWHM of 0.85-1.0 eV for Ag 3d5/2', 'XPSFitting.com'),
            (None, None, 'general', 'Oxide peaks appear at higher binding energy than metallic peaks', 'General'),
            (None, None, 'lineshape', 'Symmetric Gaussian-Lorentzian peaks are appropriate for most insulators', 'XPSFitting.com'),
            (None, None, 'general', 'Avoid adding peaks without physical justification', 'General'),
            (None, None, 'general', 'Plasmon loss features appear at fixed energy loss from main peak', 'General'),
            (None, None, 'general', 'Multiplet splitting occurs in compounds with unpaired electrons', 'XPSFitting.com'),
            (None, None, 'general', 'Coster-Kronig broadening affects L and M level line widths', 'XPSFitting.com'),

            # Element-specific rules (from XPSFitting.com)
            ('Fe', '2p', 'fitting', 'Fe 2p requires multiplet fitting for Fe2+ and Fe3+ compounds', 'XPSFitting.com'),
            ('Fe', '2p', 'satellite', 'Fe2O3 has characteristic shake-up satellite ~8 eV above 2p3/2', 'XPSFitting.com'),
            ('Fe', '2p', 'satellite', 'FeO has satellite ~6 eV above 2p3/2', 'XPSFitting.com'),
            ('Cu', '2p', 'satellite', 'Cu2+ shows strong shake-up satellites, Cu+ and Cu0 do not', 'XPSFitting.com'),
            ('Cu', '2p', 'fitting', 'Cu metal and Cu2O cannot be distinguished by 2p alone, use Auger parameter', 'XPSFitting.com'),
            ('Ni', '2p', 'fitting', 'Ni 2p requires multiplet fitting for Ni2+ compounds', 'XPSFitting.com'),
            ('Ni', '2p', 'satellite', 'NiO has complex satellite structure', 'XPSFitting.com'),
            ('Co', '2p', 'fitting', 'Co 2p requires multiplet fitting for Co2+ and Co3+', 'XPSFitting.com'),
            ('Mn', '2p', 'fitting', 'Mn 2p shows multiplet splitting for all oxidation states', 'XPSFitting.com'),
            ('Ti', '2p', 'fitting', 'TiO2 shows symmetric peaks, Ti metal is asymmetric', 'XPSFitting.com'),
            ('C', '1s', 'fitting', 'sp2 carbon (graphite) requires asymmetric line shape', 'XPSFitting.com'),
            ('C', '1s', 'fitting', 'Polymers show multiple C 1s peaks for different functional groups', 'XPSFitting.com'),
            ('Si', '2p', 'fitting', 'Si 2p doublet separation is small (0.6 eV), often fitted as single peak', 'XPSFitting.com'),
            ('Al', '2p', 'fitting', 'Al 2p doublet separation is very small (0.4 eV)', 'XPSFitting.com'),
            ('N', '1s', 'fitting', 'Organic N shows peaks at 398-402 eV depending on environment', 'XPSFitting.com'),
            ('S', '2p', 'fitting', 'S 2p doublet separation is 1.16 eV with 2:1 ratio', 'XPSFitting.com'),
            ('P', '2p', 'fitting', 'P 2p doublet separation is 0.87 eV', 'XPSFitting.com'),
            ('Zn', '2p', 'fitting', 'Zn 2p is straightforward, Auger parameter useful for oxide vs hydroxide', 'XPSFitting.com'),
        ]

        for element, orbital, rule_type, rule, source in rules:
            cursor.execute("""
                INSERT INTO fitting_rules (element, orbital, rule_type, rule, source)
                VALUES (?, ?, ?, ?, ?)
            """, (element, orbital, rule_type, rule, source))

    def _populate_doublets(self, cursor):
        """Populate doublet information"""
        doublets = [
            # p orbitals (j = 1/2, 3/2) - ratio 1:2
            ('C', '1s', 0.0, '1:0', 's orbital - no doublet'),
            ('N', '1s', 0.0, '1:0', 's orbital - no doublet'),
            ('O', '1s', 0.0, '1:0', 's orbital - no doublet'),
            ('Si', '2p', 0.6, '1:2', '2p1/2 : 2p3/2'),
            ('Al', '2p', 0.4, '1:2', '2p1/2 : 2p3/2'),
            ('S', '2p', 1.16, '1:2', '2p1/2 : 2p3/2'),
            ('P', '2p', 0.87, '1:2', '2p1/2 : 2p3/2'),
            ('Cl', '2p', 1.6, '1:2', '2p1/2 : 2p3/2'),
            ('Ti', '2p', 5.7, '1:2', '2p1/2 : 2p3/2'),
            ('V', '2p', 7.5, '1:2', '2p1/2 : 2p3/2'),
            ('Cr', '2p', 9.2, '1:2', '2p1/2 : 2p3/2'),
            ('Mn', '2p', 11.1, '1:2', '2p1/2 : 2p3/2'),
            ('Fe', '2p', 13.1, '1:2', '2p1/2 : 2p3/2'),
            ('Co', '2p', 15.0, '1:2', '2p1/2 : 2p3/2'),
            ('Ni', '2p', 17.3, '1:2', '2p1/2 : 2p3/2'),
            ('Cu', '2p', 19.8, '1:2', '2p1/2 : 2p3/2'),
            ('Zn', '2p', 23.0, '1:2', '2p1/2 : 2p3/2'),

            # d orbitals (j = 3/2, 5/2) - ratio 2:3
            ('Ag', '3d', 6.0, '2:3', '3d3/2 : 3d5/2'),
            ('Pd', '3d', 5.3, '2:3', '3d3/2 : 3d5/2'),
            ('Cd', '3d', 6.7, '2:3', '3d3/2 : 3d5/2'),
            ('In', '3d', 7.5, '2:3', '3d3/2 : 3d5/2'),
            ('Sn', '3d', 8.4, '2:3', '3d3/2 : 3d5/2'),
            ('Mo', '3d', 3.1, '2:3', '3d3/2 : 3d5/2'),
            ('Zr', '3d', 2.4, '2:3', '3d3/2 : 3d5/2'),
            ('Nb', '3d', 2.7, '2:3', '3d3/2 : 3d5/2'),
            ('W', '4f', 2.2, '3:4', '4f5/2 : 4f7/2'),
            ('Ta', '4f', 1.9, '3:4', '4f5/2 : 4f7/2'),
            ('Pt', '4f', 3.3, '3:4', '4f5/2 : 4f7/2'),
            ('Au', '4f', 3.7, '3:4', '4f5/2 : 4f7/2'),
            ('Pb', '4f', 4.9, '3:4', '4f5/2 : 4f7/2'),
            ('Bi', '4f', 5.3, '3:4', '4f5/2 : 4f7/2'),
        ]

        for element, orbital, separation, ratio, notes in doublets:
            cursor.execute("""
                INSERT INTO doublets (element, orbital, separation, ratio, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (element, orbital, separation, ratio, notes))

    # ==================== Query Methods ====================

    def get_binding_energies(self, element, line=None, be_range=None):
        """Get binding energies for an element"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if line and be_range:
            cursor.execute("""
                SELECT DISTINCT element, line, binding_energy, formula, compound_name, fwhm
                FROM nist_binding_energies
                WHERE element = ? AND line LIKE ? AND binding_energy BETWEEN ? AND ?
                ORDER BY binding_energy
            """, (element, f"%{line}%", be_range[0], be_range[1]))
        elif line:
            cursor.execute("""
                SELECT DISTINCT element, line, binding_energy, formula, compound_name, fwhm
                FROM nist_binding_energies
                WHERE element = ? AND line LIKE ?
                ORDER BY binding_energy
            """, (element, f"%{line}%"))
        else:
            cursor.execute("""
                SELECT DISTINCT element, line, binding_energy, formula, compound_name, fwhm
                FROM nist_binding_energies
                WHERE element = ?
                ORDER BY line, binding_energy
            """, (element,))

        results = cursor.fetchall()
        conn.close()

        return [{'element': r[0], 'line': r[1], 'binding_energy': r[2],
                 'formula': r[3], 'compound_name': r[4], 'fwhm': r[5]} for r in results]

    def get_all_states(self, element, orbital):
        """Get all chemical states for element/orbital"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Normalize orbital (e.g., "2p3/2" -> "2p")
        orbital_base = orbital.rstrip('0123456789/').rstrip('/')

        cursor.execute("""
            SELECT DISTINCT binding_energy, formula, compound_name, fwhm
            FROM nist_binding_energies
            WHERE element = ? AND line LIKE ?
            ORDER BY binding_energy
        """, (element, f"%{orbital_base}%"))

        results = cursor.fetchall()
        conn.close()

        return [{'binding_energy': r[0], 'formula': r[1], 'compound_name': r[2], 'fwhm': r[3]} for r in results]

    def get_fitting_rules(self, element=None, orbital=None):
        """Get fitting rules, optionally filtered by element/orbital"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if element and orbital:
            orbital_base = orbital.rstrip('0123456789/').rstrip('/')
            cursor.execute("""
                SELECT rule, rule_type, source FROM fitting_rules
                WHERE (element IS NULL OR element = ?) AND (orbital IS NULL OR orbital LIKE ?)
            """, (element, f"%{orbital_base}%"))
        elif element:
            cursor.execute("""
                SELECT rule, rule_type, source FROM fitting_rules
                WHERE element IS NULL OR element = ?
            """, (element,))
        else:
            cursor.execute("SELECT rule, rule_type, source FROM fitting_rules")

        results = cursor.fetchall()
        conn.close()

        return [{'rule': r[0], 'type': r[1], 'source': r[2]} for r in results]

    def get_doublet_info(self, element, orbital):
        """Get doublet information for element/orbital"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        orbital_base = orbital.rstrip('0123456789/').rstrip('/')

        cursor.execute("""
            SELECT separation, ratio, notes FROM doublets
            WHERE element = ? AND orbital LIKE ?
        """, (element, f"%{orbital_base}%"))

        result = cursor.fetchone()
        conn.close()

        if result:
            return {'separation': result[0], 'ratio': result[1], 'notes': result[2]}
        return None

    def build_context_for_query(self, element, orbital, binding_energy=None):
        """Build context string for ChatGPT query"""
        context_parts = []

        # Get binding energies
        states = self.get_all_states(element, orbital)
        if states:
            context_parts.append(f"=== {element} {orbital} Reference Data ===")

            # Group by compound and show representative values
            seen = set()
            for state in states:
                key = (state.get('formula', ''), round(state['binding_energy'], 1))
                if key not in seen and state['binding_energy'] > 0:
                    seen.add(key)
                    line = f"- {state.get('formula', 'Unknown')}: {state['binding_energy']:.2f} eV"
                    if state.get('compound_name'):
                        line += f" ({state['compound_name']})"
                    if state.get('fwhm') and state['fwhm'] > 0:
                        line += f" [FWHM: {state['fwhm']:.2f} eV]"
                    context_parts.append(line)

        # Get doublet info
        doublet = self.get_doublet_info(element, orbital)
        if doublet and doublet['separation'] > 0:
            context_parts.append(f"\n=== Doublet Information ===")
            context_parts.append(f"- Spin-orbit splitting: {doublet['separation']:.2f} eV")
            context_parts.append(f"- Area ratio: {doublet['ratio']}")
            context_parts.append(f"- Note: {doublet['notes']}")

        # Get relevant fitting rules
        rules = self.get_fitting_rules(element, orbital)
        if rules:
            context_parts.append(f"\n=== Fitting Rules ===")
            for rule in rules[:10]:  # Limit to 10 rules
                context_parts.append(f"- {rule['rule']} [{rule['source']}]")

        return '\n'.join(context_parts) if context_parts else "No reference data available"

    def rebuild_database(self):
        """Force rebuild of the database"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            print(f"Removed existing database: {self.db_path}")
        self._init_database()
        print("Database rebuilt successfully")

    def get_database_stats(self, element=None, line=None):
        """Get statistics about the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if element and line:
            # Count entries for specific element and line
            cursor.execute("""
                SELECT COUNT(*), COUNT(DISTINCT formula), COUNT(DISTINCT compound_name)
                FROM nist_binding_energies
                WHERE element = ? AND line LIKE ?
            """, (element, f"%{line}%"))
            total, unique_formulas, unique_compounds = cursor.fetchone()

            # Get list of compounds
            cursor.execute("""
                SELECT DISTINCT formula, compound_name, binding_energy
                FROM nist_binding_energies
                WHERE element = ? AND line LIKE ? AND formula != ''
                ORDER BY binding_energy
            """, (element, f"%{line}%"))
            compounds = cursor.fetchall()

            conn.close()
            return {
                'total_entries': total,
                'unique_formulas': unique_formulas,
                'unique_compounds': unique_compounds,
                'compounds': [{'formula': c[0], 'name': c[1], 'be': c[2]} for c in compounds]
            }

        elif element:
            # Count entries for element
            cursor.execute("""
                SELECT COUNT(*), COUNT(DISTINCT line)
                FROM nist_binding_energies
                WHERE element = ?
            """, (element,))
            total, unique_lines = cursor.fetchone()

            cursor.execute("""
                SELECT DISTINCT line FROM nist_binding_energies WHERE element = ?
            """, (element,))
            lines = [r[0] for r in cursor.fetchall()]

            conn.close()
            return {
                'total_entries': total,
                'unique_lines': unique_lines,
                'lines': lines
            }

        else:
            # Overall database stats
            cursor.execute("SELECT COUNT(*) FROM nist_binding_energies")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT element) FROM nist_binding_energies")
            unique_elements = cursor.fetchone()[0]

            cursor.execute("SELECT DISTINCT element FROM nist_binding_energies ORDER BY element")
            elements = [r[0] for r in cursor.fetchall()]

            conn.close()
            return {
                'total_entries': total,
                'unique_elements': unique_elements,
                'elements': elements
            }

    def search_database(self, query_text):
        """Search database by formula, compound name, or element"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT element, line, binding_energy, formula, compound_name
            FROM nist_binding_energies
            WHERE formula LIKE ? OR compound_name LIKE ? OR element LIKE ?
            ORDER BY element, line, binding_energy
            LIMIT 50
        """, (f"%{query_text}%", f"%{query_text}%", f"%{query_text}%"))

        results = cursor.fetchall()
        conn.close()

        return [{'element': r[0], 'line': r[1], 'be': r[2], 'formula': r[3], 'name': r[4]} for r in results]

    def add_user_correction(self, element, orbital, correction):
        """Add a user correction to the fitting rules"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if user_corrections table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_corrections'")
        if cursor.fetchone() is None:
            cursor.execute("""
                CREATE TABLE user_corrections (
                    id INTEGER PRIMARY KEY,
                    element TEXT,
                    orbital TEXT,
                    correction TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

        cursor.execute("""
            INSERT INTO user_corrections (element, orbital, correction)
            VALUES (?, ?, ?)
        """, (element, orbital, correction))

        conn.commit()
        conn.close()

    def get_user_corrections(self, element=None, orbital=None):
        """Get user corrections"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_corrections'")
        if cursor.fetchone() is None:
            conn.close()
            return []

        if element and orbital:
            cursor.execute("""
                SELECT correction FROM user_corrections
                WHERE (element IS NULL OR element = ?) AND (orbital IS NULL OR orbital = ?)
                ORDER BY timestamp DESC
            """, (element, orbital))
        else:
            cursor.execute("SELECT correction FROM user_corrections ORDER BY timestamp DESC")

        results = [r[0] for r in cursor.fetchall()]
        conn.close()
        return results