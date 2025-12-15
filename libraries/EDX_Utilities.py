"""
EDX_Utilities.py
Standalone EDX/EDS analysis utilities - replaces HyperSpy/ExSpy dependencies
for X-ray line identification, peak detection, and quantification.

This module provides:
- Complete X-ray line database for all elements (K, L, M lines)
- Element properties (atomic number, weight, density)
- X-ray line lookup functions
- Peak detection algorithms
- Signal class with axes management for compatibility

Author: KherveFitting Project
License: BSD-3-Clause
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from scipy import ndimage
from scipy.signal import find_peaks, medfilt


# =============================================================================
# X-RAY LINE DATABASE
# =============================================================================

@dataclass
class XrayLine:
    """Represents a single X-ray emission line"""
    energy_keV: float
    weight: float = 1.0  # Relative intensity weight

@dataclass
class XrayLines:
    """Collection of X-ray lines for an element"""
    Ka: Optional[XrayLine] = None
    Kb: Optional[XrayLine] = None
    La: Optional[XrayLine] = None
    Lb: Optional[XrayLine] = None
    Lg: Optional[XrayLine] = None
    Ma: Optional[XrayLine] = None
    Mb: Optional[XrayLine] = None

    def __contains__(self, item):
        return hasattr(self, item) and getattr(self, item) is not None

    def __getitem__(self, item):
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(f"Line {item} not found")

    def keys(self):
        return [k for k in ['Ka', 'Kb', 'La', 'Lb', 'Lg', 'Ma', 'Mb']
                if getattr(self, k, None) is not None]

@dataclass
class AtomicProperties:
    """Atomic properties including X-ray lines"""
    Xray_lines: XrayLines = field(default_factory=XrayLines)

@dataclass
class GeneralProperties:
    """General element properties"""
    name: str
    atomic_weight: float
    density: float = 0.0

@dataclass
class Element:
    """Complete element data structure matching ExSpy interface"""
    symbol: str
    Z: int  # Atomic number
    General_properties: GeneralProperties = None
    Atomic_properties: AtomicProperties = None

    def __post_init__(self):
        if self.General_properties is None:
            self.General_properties = GeneralProperties(name=self.symbol, atomic_weight=0.0)
        if self.Atomic_properties is None:
            self.Atomic_properties = AtomicProperties()


# Complete X-ray line database (energies in keV)
# Data from various sources including NIST and Bearden's tables
XRAY_LINE_DATA = {
    # Format: 'Symbol': (Z, atomic_weight, density, Ka, Kb, La, Lb, Ma, Mb)
    # None means line not significant/available
    'H':  (1, 1.008, 0.00009, None, None, None, None, None, None),
    'He': (2, 4.003, 0.00018, None, None, None, None, None, None),
    'Li': (3, 6.941, 0.534, 0.054, None, None, None, None, None),
    'Be': (4, 9.012, 1.85, 0.109, None, None, None, None, None),
    'B':  (5, 10.81, 2.34, 0.183, None, None, None, None, None),
    'C':  (6, 12.01, 2.27, 0.277, None, None, None, None, None),
    'N':  (7, 14.01, 0.00125, 0.392, None, None, None, None, None),
    'O':  (8, 16.00, 0.00143, 0.525, None, None, None, None, None),
    'F':  (9, 19.00, 0.0017, 0.677, None, None, None, None, None),
    'Ne': (10, 20.18, 0.0009, 0.849, None, None, None, None, None),
    'Na': (11, 22.99, 0.97, 1.041, 1.071, None, None, None, None),
    'Mg': (12, 24.31, 1.74, 1.254, 1.302, None, None, None, None),
    'Al': (13, 26.98, 2.70, 1.487, 1.557, None, None, None, None),
    'Si': (14, 28.09, 2.33, 1.740, 1.836, None, None, None, None),
    'P':  (15, 30.97, 1.82, 2.013, 2.139, None, None, None, None),
    'S':  (16, 32.07, 2.07, 2.307, 2.464, None, None, None, None),
    'Cl': (17, 35.45, 0.0032, 2.622, 2.815, None, None, None, None),
    'Ar': (18, 39.95, 0.0018, 2.957, 3.190, None, None, None, None),
    'K':  (19, 39.10, 0.86, 3.313, 3.590, None, None, None, None),
    'Ca': (20, 40.08, 1.55, 3.691, 4.012, 0.341, 0.345, None, None),
    'Sc': (21, 44.96, 2.99, 4.090, 4.460, 0.395, 0.400, None, None),
    'Ti': (22, 47.87, 4.54, 4.510, 4.931, 0.452, 0.458, None, None),
    'V':  (23, 50.94, 6.11, 4.952, 5.427, 0.511, 0.519, None, None),
    'Cr': (24, 52.00, 7.19, 5.414, 5.946, 0.573, 0.583, None, None),
    'Mn': (25, 54.94, 7.44, 5.898, 6.490, 0.637, 0.649, None, None),
    'Fe': (26, 55.85, 7.87, 6.403, 7.057, 0.705, 0.718, None, None),
    'Co': (27, 58.93, 8.90, 6.930, 7.649, 0.776, 0.791, None, None),
    'Ni': (28, 58.69, 8.91, 7.477, 8.264, 0.851, 0.868, None, None),
    'Cu': (29, 63.55, 8.96, 8.047, 8.904, 0.930, 0.949, None, None),
    'Zn': (30, 65.39, 7.13, 8.638, 9.571, 1.012, 1.034, None, None),
    'Ga': (31, 69.72, 5.91, 9.251, 10.263, 1.098, 1.124, None, None),
    'Ge': (32, 72.64, 5.32, 9.886, 10.981, 1.188, 1.218, None, None),
    'As': (33, 74.92, 5.73, 10.543, 11.725, 1.282, 1.317, None, None),
    'Se': (34, 78.96, 4.79, 11.222, 12.495, 1.379, 1.419, None, None),
    'Br': (35, 79.90, 3.12, 11.923, 13.291, 1.480, 1.526, None, None),
    'Kr': (36, 83.80, 0.0037, 12.648, 14.112, 1.586, 1.636, None, None),
    'Rb': (37, 85.47, 1.53, 13.394, 14.961, 1.694, 1.752, None, None),
    'Sr': (38, 87.62, 2.54, 14.164, 15.834, 1.806, 1.871, None, None),
    'Y':  (39, 88.91, 4.47, 14.957, 16.737, 1.922, 1.996, None, None),
    'Zr': (40, 91.22, 6.51, 15.774, 17.666, 2.042, 2.124, None, None),
    'Nb': (41, 92.91, 8.57, 16.614, 18.621, 2.166, 2.257, None, None),
    'Mo': (42, 95.94, 10.22, 17.479, 19.607, 2.293, 2.394, None, None),
    'Tc': (43, 98.00, 11.5, 18.367, 20.585, 2.424, 2.536, None, None),
    'Ru': (44, 101.07, 12.37, 19.279, 21.656, 2.558, 2.683, None, None),
    'Rh': (45, 102.91, 12.41, 20.214, 22.723, 2.696, 2.834, None, None),
    'Pd': (46, 106.42, 12.02, 21.175, 23.818, 2.838, 2.990, None, None),
    'Ag': (47, 107.87, 10.50, 22.162, 24.942, 2.984, 3.150, None, None),
    'Cd': (48, 112.41, 8.65, 23.173, 26.093, 3.133, 3.316, None, None),
    'In': (49, 114.82, 7.31, 24.209, 27.274, 3.286, 3.487, None, None),
    'Sn': (50, 118.71, 7.31, 25.270, 28.483, 3.443, 3.662, None, None),
    'Sb': (51, 121.76, 6.69, 26.357, 29.723, 3.604, 3.843, None, None),
    'Te': (52, 127.60, 6.24, 27.471, 30.993, 3.769, 4.029, None, None),
    'I':  (53, 126.90, 4.93, 28.610, 32.292, 3.937, 4.220, None, None),
    'Xe': (54, 131.29, 0.0059, 29.775, 33.620, 4.109, 4.422, None, None),
    'Cs': (55, 132.91, 1.87, 30.968, 34.984, 4.286, 4.619, None, None),
    'Ba': (56, 137.33, 3.59, 32.191, 36.376, 4.466, 4.827, 0.781, 0.796),
    'La': (57, 138.91, 6.15, 33.440, 37.799, 4.650, 5.042, 0.833, 0.849),
    'Ce': (58, 140.12, 6.77, 34.717, 39.255, 4.839, 5.262, 0.883, 0.902),
    'Pr': (59, 140.91, 6.77, 36.023, 40.746, 5.033, 5.488, 0.929, 0.951),
    'Nd': (60, 144.24, 7.01, 37.359, 42.269, 5.229, 5.721, 0.978, 1.000),
    'Pm': (61, 145.00, 7.26, 38.720, 43.811, 5.432, 5.961, 1.027, 1.052),
    'Sm': (62, 150.36, 7.52, 40.111, 45.400, 5.635, 6.204, 1.081, 1.107),
    'Eu': (63, 151.96, 5.24, 41.529, 47.027, 5.845, 6.456, 1.131, 1.161),
    'Gd': (64, 157.25, 7.90, 42.983, 48.688, 6.056, 6.712, 1.185, 1.217),
    'Tb': (65, 158.93, 8.23, 44.470, 50.391, 6.272, 6.977, 1.240, 1.275),
    'Dy': (66, 162.50, 8.55, 45.985, 52.130, 6.494, 7.247, 1.293, 1.332),
    'Ho': (67, 164.93, 8.80, 47.528, 53.904, 6.719, 7.525, 1.348, 1.390),
    'Er': (68, 167.26, 9.07, 49.099, 55.690, 6.948, 7.810, 1.406, 1.453),
    'Tm': (69, 168.93, 9.32, 50.730, 57.576, 7.179, 8.100, 1.462, 1.514),
    'Yb': (70, 173.04, 6.90, 52.360, 59.352, 7.414, 8.401, 1.521, 1.576),
    'Lu': (71, 174.97, 9.84, 54.063, 61.290, 7.654, 8.708, 1.581, 1.640),
    'Hf': (72, 178.49, 13.31, 55.757, 63.210, 7.898, 9.021, 1.644, 1.706),
    'Ta': (73, 180.95, 16.65, 57.524, 65.210, 8.145, 9.341, 1.709, 1.775),
    'W':  (74, 183.84, 19.35, 59.310, 67.233, 8.396, 9.670, 1.774, 1.843),
    'Re': (75, 186.21, 21.04, 61.131, 69.298, 8.651, 10.008, 1.842, 1.914),
    'Os': (76, 190.23, 22.59, 62.991, 71.404, 8.910, 10.354, 1.910, 1.987),
    'Ir': (77, 192.22, 22.56, 64.886, 73.549, 9.174, 10.706, 1.980, 2.061),
    'Pt': (78, 195.08, 21.45, 66.820, 75.736, 9.441, 11.069, 2.050, 2.136),
    'Au': (79, 196.97, 19.32, 68.794, 77.968, 9.712, 11.439, 2.123, 2.213),
    'Hg': (80, 200.59, 13.55, 70.821, 80.258, 9.987, 11.823, 2.195, 2.291),
    'Tl': (81, 204.38, 11.85, 72.860, 82.558, 10.268, 12.210, 2.270, 2.371),
    'Pb': (82, 207.20, 11.35, 74.957, 84.922, 10.549, 12.611, 2.345, 2.453),
    'Bi': (83, 208.98, 9.75, 77.095, 87.335, 10.836, 13.021, 2.423, 2.537),
    'Po': (84, 209.00, 9.20, 79.290, 89.809, 11.128, 13.443, 2.502, 2.621),
    'At': (85, 210.00, 7.00, 81.520, 92.315, 11.424, 13.873, 2.582, 2.708),
    'Rn': (86, 222.00, 0.0097, 83.800, 94.877, 11.724, 14.316, 2.663, 2.795),
    'Fr': (87, 223.00, 1.87, 86.100, 97.470, 12.029, 14.770, 2.746, 2.884),
    'Ra': (88, 226.00, 5.50, 88.470, 100.119, 12.338, 15.233, 2.830, 2.975),
    'Ac': (89, 227.00, 10.07, 90.884, 102.846, 12.650, 15.712, 2.916, 3.067),
    'Th': (90, 232.04, 11.72, 93.334, 105.592, 12.966, 16.200, 3.004, 3.161),
    'Pa': (91, 231.04, 15.37, 95.851, 108.408, 13.291, 16.700, 3.092, 3.256),
    'U':  (92, 238.03, 18.95, 98.428, 111.289, 13.613, 17.218, 3.171, 3.336),
}

# K-alpha to K-beta intensity ratios (approximate)
KB_KA_RATIO = 0.13  # Kb is typically ~13% of Ka intensity

# L-alpha to L-beta intensity ratios (approximate)
LB_LA_RATIO = 0.70  # Lb is typically ~70% of La intensity


def _create_element(symbol: str, data: tuple) -> Element:
    """Create Element object from raw data tuple"""
    Z, atomic_weight, density, Ka, Kb, La, Lb, Ma, Mb = data

    xray_lines = XrayLines(
        Ka=XrayLine(Ka, 1.0) if Ka else None,
        Kb=XrayLine(Kb, KB_KA_RATIO) if Kb else None,
        La=XrayLine(La, 1.0) if La else None,
        Lb=XrayLine(Lb, LB_LA_RATIO) if Lb else None,
        Ma=XrayLine(Ma, 1.0) if Ma else None,
        Mb=XrayLine(Mb, 0.6) if Mb else None,
    )

    return Element(
        symbol=symbol,
        Z=Z,
        General_properties=GeneralProperties(
            name=symbol,
            atomic_weight=atomic_weight,
            density=density
        ),
        Atomic_properties=AtomicProperties(Xray_lines=xray_lines)
    )


class ElementDatabase:
    """
    Database of elements with X-ray line data.
    Compatible with ExSpy's elements interface.
    """

    def __init__(self):
        self._elements: Dict[str, Element] = {}
        self._load_database()

    def _load_database(self):
        """Load all elements from the data dictionary"""
        for symbol, data in XRAY_LINE_DATA.items():
            self._elements[symbol] = _create_element(symbol, data)

    def __getitem__(self, symbol: str) -> Element:
        """Get element by symbol"""
        if symbol not in self._elements:
            raise KeyError(f"Element '{symbol}' not found in database")
        return self._elements[symbol]

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._elements

    def __iter__(self):
        return iter(self._elements)

    def keys(self):
        return self._elements.keys()

    def values(self):
        return self._elements.values()

    def items(self):
        return self._elements.items()

    def get(self, symbol: str, default=None) -> Optional[Element]:
        return self._elements.get(symbol, default)


# Global element database instance (replaces exspy.material.elements)
elements = ElementDatabase()


# =============================================================================
# X-RAY LINE LOOKUP FUNCTIONS
# =============================================================================

def get_xray_lines_near_energy(energy_keV: float,
                                tolerance: float = 0.1,
                                only_lines: List[str] = None) -> List[Tuple[str, str, float]]:
    """
    Find X-ray lines near a given energy.

    Replaces exspy.utils.eds.get_xray_lines_near_energy

    Parameters
    ----------
    energy_keV : float
        Energy to search around (in keV)
    tolerance : float
        Energy tolerance in keV (default 0.1)
    only_lines : list, optional
        List of line types to consider (e.g., ['Ka', 'La'])

    Returns
    -------
    list of tuples
        Each tuple is (element_symbol, line_type, line_energy)
        Sorted by distance from target energy
    """
    if only_lines is None:
        only_lines = ['Ka', 'Kb', 'La', 'Lb', 'Ma', 'Mb']

    matches = []

    for symbol, elem in elements.items():
        if elem.Atomic_properties is None:
            continue
        xray = elem.Atomic_properties.Xray_lines
        if xray is None:
            continue

        for line_type in only_lines:
            line = getattr(xray, line_type, None)
            if line is not None and line.energy_keV is not None:
                diff = abs(line.energy_keV - energy_keV)
                if diff <= tolerance:
                    matches.append((symbol, line_type, line.energy_keV, diff))

    # Sort by distance from target energy
    matches.sort(key=lambda x: x[3])

    # Return without the distance
    return [(m[0], m[1], m[2]) for m in matches]


def get_element_xray_lines(symbol: str) -> Dict[str, float]:
    """
    Get all X-ray line energies for an element.

    Parameters
    ----------
    symbol : str
        Element symbol

    Returns
    -------
    dict
        Dictionary mapping line type to energy in keV
    """
    if symbol not in elements:
        return {}

    elem = elements[symbol]
    if elem.Atomic_properties is None or elem.Atomic_properties.Xray_lines is None:
        return {}

    xray = elem.Atomic_properties.Xray_lines
    result = {}

    for line_type in ['Ka', 'Kb', 'La', 'Lb', 'Lg', 'Ma', 'Mb']:
        line = getattr(xray, line_type, None)
        if line is not None and line.energy_keV is not None:
            result[line_type] = line.energy_keV

    return result


def get_all_lines_in_range(e_min: float, e_max: float,
                           line_types: List[str] = None) -> List[Tuple[str, str, float]]:
    """
    Get all X-ray lines within an energy range.

    Parameters
    ----------
    e_min : float
        Minimum energy in keV
    e_max : float
        Maximum energy in keV
    line_types : list, optional
        Line types to include (default: all)

    Returns
    -------
    list of tuples
        (element_symbol, line_type, energy_keV) sorted by energy
    """
    if line_types is None:
        line_types = ['Ka', 'Kb', 'La', 'Lb', 'Ma', 'Mb']

    lines = []

    for symbol, elem in elements.items():
        if elem.Atomic_properties is None:
            continue
        xray = elem.Atomic_properties.Xray_lines
        if xray is None:
            continue

        for line_type in line_types:
            line = getattr(xray, line_type, None)
            if line is not None and line.energy_keV is not None:
                if e_min <= line.energy_keV <= e_max:
                    lines.append((symbol, line_type, line.energy_keV))

    lines.sort(key=lambda x: x[2])
    return lines


# =============================================================================
# PEAK DETECTION
# =============================================================================

def find_peaks1D_ohaver(data: np.ndarray,
                        maxpeakn: int = 100,
                        medfilt_radius: int = 5,
                        peakgroup: int = 10,
                        amp_thresh: float = None,
                        slope_thresh: float = 0,
                        energy_axis: np.ndarray = None,
                        scale: float = 1.0,
                        offset: float = 0.0) -> np.ndarray:
    """
    Peak detection using the Ohaver algorithm.

    Replaces HyperSpy's find_peaks1D_ohaver method.

    Parameters
    ----------
    data : np.ndarray
        1D spectrum data
    maxpeakn : int
        Maximum number of peaks to find
    medfilt_radius : int
        Radius for median filter smoothing
    peakgroup : int
        Number of points around peak for fitting
    amp_thresh : float
        Minimum amplitude threshold (default: 2% of max)
    slope_thresh : float
        Minimum slope threshold
    energy_axis : np.ndarray, optional
        Pre-computed energy axis values
    scale : float
        Energy scale (keV per channel)
    offset : float
        Energy offset (keV)

    Returns
    -------
    np.ndarray
        Array of (energy, height, width) tuples - energy in keV if scale/offset provided
    """
    if len(data) < 5:
        return np.array([])

    # Apply median filter for smoothing
    if medfilt_radius > 0:
        kernel_size = 2 * medfilt_radius + 1
        if kernel_size > len(data):
            kernel_size = len(data) if len(data) % 2 == 1 else len(data) - 1
        smoothed = medfilt(data.astype(float), kernel_size)
    else:
        smoothed = data.astype(float)

    # Default amplitude threshold
    if amp_thresh is None:
        amp_thresh = np.max(smoothed) * 0.02

    # Use scipy find_peaks for more robust detection
    from scipy.signal import find_peaks as scipy_find_peaks

    # Find peaks using scipy - use lower prominence for better sensitivity
    peak_indices, properties = scipy_find_peaks(
        smoothed,
        height=amp_thresh,
        distance=max(1, peakgroup // 2),
        prominence=amp_thresh * 0.01  # Lower prominence for better sensitivity
    )

    # If scipy didn't find enough peaks, try derivative method
    if len(peak_indices) < 3:
        # Fallback to derivative method
        deriv = np.gradient(smoothed)
        deriv_peaks = []
        for i in range(2, len(deriv) - 2):
            # Check for sign change in derivative (peak)
            if deriv[i-1] > 0 and deriv[i+1] < 0:
                if smoothed[i] >= amp_thresh:
                    deriv_peaks.append(i)

        # Combine with scipy results
        all_peaks = set(peak_indices.tolist()) | set(deriv_peaks)
        peak_indices = np.array(sorted(all_peaks))

    if len(peak_indices) == 0:
        return np.array([])

    peaks = []
    for i in peak_indices:
        # Refine peak position using parabolic interpolation
        if i > 0 and i < len(smoothed) - 1:
            y0, y1, y2 = smoothed[i-1], smoothed[i], smoothed[i+1]
            denom = 2 * y1 - y0 - y2
            if abs(denom) > 1e-10:
                delta = 0.5 * (y0 - y2) / denom
                delta = max(-1, min(1, delta))
                peak_pos_idx = i + delta
                peak_height = y1 - 0.25 * (y0 - y2) * delta
            else:
                peak_pos_idx = float(i)
                peak_height = y1
        else:
            peak_pos_idx = float(i)
            peak_height = smoothed[i]

        # Convert index to energy
        if energy_axis is not None and len(energy_axis) > i:
            # Interpolate energy value
            idx_floor = int(np.floor(peak_pos_idx))
            idx_ceil = min(int(np.ceil(peak_pos_idx)), len(energy_axis) - 1)
            if idx_floor == idx_ceil:
                peak_energy = energy_axis[idx_floor]
            else:
                frac = peak_pos_idx - idx_floor
                peak_energy = energy_axis[idx_floor] * (1 - frac) + energy_axis[idx_ceil] * frac
        else:
            peak_energy = peak_pos_idx * scale + offset

        # Estimate peak width (FWHM) in energy units
        half_max = (peak_height + smoothed.min()) / 2
        left_idx = i
        right_idx = i
        while left_idx > 0 and smoothed[left_idx] > half_max:
            left_idx -= 1
        while right_idx < len(smoothed) - 1 and smoothed[right_idx] > half_max:
            right_idx += 1
        width_channels = float(right_idx - left_idx)
        width_energy = width_channels * scale  # Convert to energy units

        peaks.append((peak_energy, peak_height, width_energy))

    # Sort by height and limit to maxpeakn
    peaks.sort(key=lambda x: x[1], reverse=True)
    peaks = peaks[:maxpeakn]

    if not peaks:
        return np.array([])

    return np.array(peaks, dtype=float)


def find_peaks_scipy(data: np.ndarray,
                     height: float = None,
                     threshold: float = None,
                     distance: int = None,
                     prominence: float = None,
                     width: int = None) -> Tuple[np.ndarray, dict]:
    """
    Peak detection using scipy.signal.find_peaks.

    Parameters
    ----------
    data : np.ndarray
        1D spectrum data
    height : float
        Minimum peak height
    threshold : float
        Minimum threshold of peaks
    distance : int
        Minimum distance between peaks
    prominence : float
        Minimum prominence of peaks
    width : int
        Minimum width of peaks

    Returns
    -------
    tuple
        (peak_indices, properties_dict)
    """
    return find_peaks(data, height=height, threshold=threshold,
                     distance=distance, prominence=prominence, width=width)


# =============================================================================
# SIGNAL CLASS (HyperSpy compatibility)
# =============================================================================

class Axis:
    """Single axis with scale, offset, and units"""

    def __init__(self, size: int = 0, scale: float = 1.0, offset: float = 0.0,
                 name: str = '', units: str = ''):
        self.size = size
        self.scale = scale
        self.offset = offset
        self.name = name
        self.units = units

    @property
    def axis(self) -> np.ndarray:
        """Generate axis values array"""
        return np.arange(self.size) * self.scale + self.offset

    def value2index(self, value: float) -> int:
        """Convert axis value to index"""
        return int(round((value - self.offset) / self.scale))

    def index2value(self, index: int) -> float:
        """Convert index to axis value"""
        return index * self.scale + self.offset


class AxesManager:
    """Manages axes for multidimensional signals"""

    def __init__(self, shape: tuple):
        self._axes = []
        self._signal_axes = []
        self._navigation_axes = []

        # Create default axes based on shape
        for i, size in enumerate(shape):
            axis = Axis(size=size, name=f'axis-{i}')
            self._axes.append(axis)

        # By default, last axis is signal axis
        if self._axes:
            self._signal_axes = [self._axes[-1]]
            self._navigation_axes = self._axes[:-1]

    def __getitem__(self, index: int) -> Axis:
        return self._axes[index]

    def __len__(self):
        return len(self._axes)

    @property
    def signal_axes(self) -> List[Axis]:
        return self._signal_axes

    @property
    def navigation_axes(self) -> List[Axis]:
        return self._navigation_axes

    @property
    def shape(self) -> tuple:
        return tuple(ax.size for ax in self._axes)


class Signal1D:
    """
    1D signal class compatible with HyperSpy interface.

    Provides basic functionality for spectrum handling.
    """

    def __init__(self, data: np.ndarray):
        """
        Initialize signal with data.

        Parameters
        ----------
        data : np.ndarray
            Signal data (can be 1D or multidimensional)
        """
        self.data = np.asarray(data)
        self.axes_manager = AxesManager(self.data.shape)
        self.metadata = {}
        self._signal_type = None

    def set_signal_type(self, signal_type: str):
        """Set the signal type (e.g., 'EDS_SEM')"""
        self._signal_type = signal_type

    def find_peaks1D_ohaver(self, maxpeakn: int = 100,
                            medfilt_radius: int = 5,
                            peakgroup: int = 10,
                            amp_thresh: float = None,
                            slope_thresh: float = 0) -> np.ndarray:
        """
        Find peaks in 1D signal using Ohaver algorithm.

        Returns array of (energy, height, width) where energy is
        converted using the axis calibration.
        """
        # Get 1D data (flatten if needed)
        if self.data.ndim > 1:
            spectrum = self.data.flatten()
        else:
            spectrum = self.data

        # Get axis calibration
        axis = self.axes_manager[0]
        scale = axis.scale
        offset = axis.offset
        energy_axis = axis.axis

        # Find peaks with energy conversion
        peaks = find_peaks1D_ohaver(
            spectrum,
            maxpeakn=maxpeakn,
            medfilt_radius=medfilt_radius,
            peakgroup=peakgroup,
            amp_thresh=amp_thresh,
            slope_thresh=slope_thresh,
            energy_axis=energy_axis,
            scale=scale,
            offset=offset
        )

        if len(peaks) == 0:
            return np.array([[]])

        # Return wrapped in list for HyperSpy compatibility
        return np.array([peaks])


class Signal2D:
    """
    2D signal class for images/maps.
    """

    def __init__(self, data: np.ndarray):
        self.data = np.asarray(data)
        self.axes_manager = AxesManager(self.data.shape)
        self.metadata = {}


# =============================================================================
# FILE LOADING UTILITIES
# =============================================================================

def load_emsa(filepath: str) -> dict:
    """
    Load EMSA/MSA format spectrum file.

    Parameters
    ----------
    filepath : str
        Path to EMSA file

    Returns
    -------
    dict
        Dictionary with 'data', 'energy', and 'metadata'
    """
    metadata = {}
    data_lines = []
    in_data = False

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()

            if line.startswith('#'):
                # Parse header
                if ':' in line:
                    key, _, value = line[1:].partition(':')
                    key = key.strip()
                    value = value.strip()
                    metadata[key] = value

                    # Check for data start
                    if key.upper() == 'SPECTRUM':
                        in_data = True
            elif in_data and line:
                # Parse data
                try:
                    parts = line.replace(',', ' ').split()
                    if len(parts) >= 2:
                        data_lines.append((float(parts[0]), float(parts[1])))
                    elif len(parts) == 1:
                        data_lines.append(float(parts[0]))
                except ValueError:
                    continue

    if not data_lines:
        raise ValueError("No spectrum data found in file")

    # Determine format
    if isinstance(data_lines[0], tuple):
        energy = np.array([d[0] for d in data_lines])
        counts = np.array([d[1] for d in data_lines])
    else:
        counts = np.array(data_lines)
        # Generate energy axis from metadata
        offset = float(metadata.get('XPERCHAN', metadata.get('OFFSET', 0)))
        scale = float(metadata.get('XPERCHAN', 0.01))
        energy = np.arange(len(counts)) * scale + offset

    return {
        'data': counts,
        'energy': energy,
        'metadata': metadata
    }


def load_csv_spectrum(filepath: str,
                      energy_col: int = 0,
                      counts_col: int = 1,
                      skip_rows: int = 0,
                      delimiter: str = ',') -> dict:
    """
    Load spectrum from CSV file.

    Parameters
    ----------
    filepath : str
        Path to CSV file
    energy_col : int
        Column index for energy values
    counts_col : int
        Column index for counts/intensity values
    skip_rows : int
        Number of header rows to skip
    delimiter : str
        Column delimiter

    Returns
    -------
    dict
        Dictionary with 'data', 'energy', and 'metadata'
    """
    data = np.loadtxt(filepath, delimiter=delimiter, skiprows=skip_rows)

    if data.ndim == 1:
        counts = data
        energy = np.arange(len(counts))
    else:
        energy = data[:, energy_col]
        counts = data[:, counts_col]

    return {
        'data': counts,
        'energy': energy,
        'metadata': {'source_file': filepath}
    }


# =============================================================================
# QUANTIFICATION UTILITIES
# =============================================================================

# Default k-factors for common elements (relative to Si Ka = 1.0)
# These are approximate values for ~20 kV SEM-EDS
DEFAULT_KFACTORS = {
    'C_Ka': 3.17,
    'N_Ka': 2.58,
    'O_Ka': 1.98,
    'F_Ka': 1.63,
    'Na_Ka': 0.97,
    'Mg_Ka': 0.89,
    'Al_Ka': 0.87,
    'Si_Ka': 1.00,  # Reference
    'P_Ka': 1.08,
    'S_Ka': 1.06,
    'Cl_Ka': 1.04,
    'K_Ka': 1.03,
    'Ca_Ka': 1.04,
    'Ti_Ka': 1.07,
    'V_Ka': 1.08,
    'Cr_Ka': 1.10,
    'Mn_Ka': 1.11,
    'Fe_Ka': 1.13,
    'Co_Ka': 1.15,
    'Ni_Ka': 1.17,
    'Cu_Ka': 1.20,
    'Zn_Ka': 1.22,
    'Ga_Ka': 1.24,
    'Ge_Ka': 1.26,
    'As_Ka': 1.28,
    'Se_Ka': 1.30,
    'Br_Ka': 1.32,
    'Sr_Ka': 1.45,
    'Y_Ka': 1.48,
    'Zr_Ka': 1.51,
    'Nb_Ka': 1.54,
    'Mo_Ka': 1.57,
    'Ag_Ka': 1.75,
    'Sn_Ka': 1.85,
    'Ba_La': 1.95,
    'La_La': 1.98,
    'Ce_La': 2.01,
    'Pb_La': 2.45,
    'Pb_Ma': 2.80,
    'Au_La': 2.35,
    'Au_Ma': 2.65,
}


def get_kfactor(element: str, line: str = 'Ka') -> float:
    """
    Get k-factor for element and line.

    Parameters
    ----------
    element : str
        Element symbol
    line : str
        X-ray line type (Ka, La, Ma, etc.)

    Returns
    -------
    float
        k-factor value (1.0 if not found)
    """
    key = f"{element}_{line}"
    return DEFAULT_KFACTORS.get(key, 1.0)


def cliff_lorimer_quantification(intensities: Dict[str, float],
                                  kfactors: Dict[str, float] = None) -> Dict[str, float]:
    """
    Calculate atomic percentages using Cliff-Lorimer method.

    Parameters
    ----------
    intensities : dict
        Dictionary mapping element_line to intensity
        e.g., {'Fe_Ka': 1000, 'O_Ka': 500}
    kfactors : dict, optional
        k-factors for each element_line

    Returns
    -------
    dict
        Dictionary mapping element to atomic percentage
    """
    if kfactors is None:
        kfactors = DEFAULT_KFACTORS

    # Calculate C*I/k for each element
    weighted = {}
    for elem_line, intensity in intensities.items():
        k = kfactors.get(elem_line, 1.0)
        elem = elem_line.split('_')[0]
        if elem not in weighted:
            weighted[elem] = 0
        weighted[elem] += intensity / k

    # Normalize to 100%
    total = sum(weighted.values())
    if total > 0:
        return {elem: (val / total) * 100 for elem, val in weighted.items()}
    return weighted


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def identify_peak(energy_keV: float, tolerance: float = 0.15) -> Optional[Tuple[str, str]]:
    """
    Identify the most likely element and line for a peak energy.

    Parameters
    ----------
    energy_keV : float
        Peak energy in keV
    tolerance : float
        Search tolerance in keV

    Returns
    -------
    tuple or None
        (element_symbol, line_type) or None if not found
    """
    matches = get_xray_lines_near_energy(energy_keV, tolerance)
    if matches:
        return (matches[0][0], matches[0][1])
    return None


def get_element_info(symbol: str) -> dict:
    """
    Get comprehensive information about an element.

    Parameters
    ----------
    symbol : str
        Element symbol

    Returns
    -------
    dict
        Dictionary with element properties and X-ray lines
    """
    if symbol not in elements:
        return {}

    elem = elements[symbol]

    info = {
        'symbol': symbol,
        'Z': elem.Z,
        'name': elem.General_properties.name,
        'atomic_weight': elem.General_properties.atomic_weight,
        'density': elem.General_properties.density,
        'xray_lines': get_element_xray_lines(symbol)
    }

    return info


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

# For drop-in compatibility with imports like:
# from EDX_Utilities import elements
# from EDX_Utilities import get_xray_lines_near_energy

__all__ = [
    'elements',
    'Element',
    'ElementDatabase',
    'XrayLine',
    'XrayLines',
    'get_xray_lines_near_energy',
    'get_element_xray_lines',
    'get_all_lines_in_range',
    'find_peaks1D_ohaver',
    'find_peaks_scipy',
    'Signal1D',
    'Signal2D',
    'Axis',
    'AxesManager',
    'load_emsa',
    'load_csv_spectrum',
    'get_kfactor',
    'cliff_lorimer_quantification',
    'identify_peak',
    'get_element_info',
    'DEFAULT_KFACTORS',
]