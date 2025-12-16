"""
EELS_Utilities.py
Standalone EELS (Electron Energy Loss Spectroscopy) analysis utilities
Replaces HyperSpy dependencies for .dm3/.dm4 file import and analysis.

This module provides:
- DM3/DM4 file reading (Digital Micrograph format) using ncempy or hyperspy
- HDF5 EELS data loading
- Signal class with axes management for compatibility
- Basic EELS data structures

Author: KherveFitting Project
License: BSD-3-Clause
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Any, Dict


# =============================================================================
# AXES MANAGEMENT (compatible with HyperSpy interface)
# =============================================================================

@dataclass
class Axis:
    """Axis calibration for signal dimensions"""
    size: int
    scale: float = 1.0
    offset: float = 0.0
    units: str = ''
    name: str = ''

    @property
    def axis(self) -> np.ndarray:
        """Generate axis values"""
        return np.arange(self.size) * self.scale + self.offset


class AxesManager:
    """
    Manages axes for signals (compatible with HyperSpy).

    Convention: last axis is signal axis, others are navigation axes
    """

    def __init__(self, shape: tuple):
        self._axes = []
        self._signal_axes = []
        self._navigation_axes = []

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


# =============================================================================
# SIGNAL CLASSES (compatible with HyperSpy interface)
# =============================================================================

class Signal1D:
    """
    1D signal class compatible with HyperSpy interface.
    Used for EELS spectrum handling.
    """

    def __init__(self, data: np.ndarray):
        """
        Initialize signal with data.

        Parameters
        ----------
        data : np.ndarray
            Signal data (can be 1D or multidimensional for spectrum images)
        """
        self.data = np.asarray(data)
        self.axes_manager = AxesManager(self.data.shape)
        self.metadata = {}
        self._signal_type = 'EELS'

    def set_signal_type(self, signal_type: str):
        """Set the signal type (e.g., 'EELS')"""
        self._signal_type = signal_type

    def sum(self, axis=None):
        """Sum signal along specified axis"""
        if axis is None:
            # Sum over navigation axes (spatial dimensions)
            if len(self.data.shape) > 1:
                summed_data = np.sum(self.data, axis=tuple(range(len(self.data.shape) - 1)))
            else:
                summed_data = self.data
        else:
            summed_data = np.sum(self.data, axis=axis)

        return Signal1D(summed_data)


# =============================================================================
# DM3/DM4 FILE READER (Digital Micrograph format)
# =============================================================================

def load_dm3_dm4(filepath: str) -> Signal1D:
    """
    Load DM3/DM4 file using available libraries.

    Tries multiple methods in order:
    1. ncempy (lightweight, no dependencies)
    2. hyperspy (if available as fallback)

    Parameters
    ----------
    filepath : str
        Path to DM3/DM4 file

    Returns
    -------
    Signal1D
        EELS signal object
    """
    # Try ncempy first (recommended for DM3/DM4)
    try:
        import ncempy.io.dm as dm

        dm_file = dm.fileDM(filepath)

        # Get dataset (usually index 0 is the main data)
        data_dict = dm_file.getDataset(0)
        data = data_dict['data']

        # Get calibration
        pixelSize = data_dict.get('pixelSize', [])
        pixelOrigin = data_dict.get('pixelOrigin', [])
        pixelUnit = data_dict.get('pixelUnit', [])

        print(f"DM3/DM4 data shape: {data.shape}")
        print(f"Pixel sizes: {pixelSize}")
        print(f"Pixel origins: {pixelOrigin}")
        print(f"Pixel units: {pixelUnit}")

        # DETECT AXIS ORDER: Find which axis is the energy axis
        # Energy axis has units 'eV' and typically larger size (hundreds to thousands)
        energy_axis_idx = None

        for i, unit in enumerate(pixelUnit):
            unit_str = str(unit).lower() if unit else ''
            if 'ev' in unit_str or 'electron' in unit_str:
                energy_axis_idx = i
                print(f"Detected energy axis at index {i}")
                break

        # If energy axis is first (common in some EELS formats), need to transpose
        if energy_axis_idx == 0 and len(data.shape) == 3:
            print(f"Energy axis is FIRST - transposing data from (E,Y,X) to (Y,X,E)")
            # Transpose from (Energy, Y, X) to (Y, X, Energy)
            data = np.transpose(data, (1, 2, 0))
            # Reorder calibration arrays
            pixelSize = [pixelSize[1], pixelSize[2], pixelSize[0]]
            pixelOrigin = [pixelOrigin[1], pixelOrigin[2], pixelOrigin[0]]
            pixelUnit = [pixelUnit[1], pixelUnit[2], pixelUnit[0]]
            print(f"New data shape after transpose: {data.shape}")
            print(f"New pixel units order: {pixelUnit}")

        # Create signal
        signal = Signal1D(data)

        # Set up axes with calibration
        # Convention: for 3D data (y, x, energy), axes are [y, x, energy]
        for i, axis in enumerate(signal.axes_manager._axes):
            if i < len(pixelSize) and pixelSize[i] is not None:
                axis.scale = float(pixelSize[i])
            else:
                axis.scale = 1.0

            if i < len(pixelOrigin) and pixelOrigin[i] is not None:
                axis.offset = float(pixelOrigin[i])
            else:
                axis.offset = 0.0

            if i < len(pixelUnit) and pixelUnit[i]:
                unit_str = str(pixelUnit[i])
                # Clean up unit string
                if unit_str.lower() in ['nm', 'nanometer', 'nanometers']:
                    axis.units = 'nm'
                elif unit_str.lower() in ['µm', 'um', 'micrometer', 'micrometers', 'micron']:
                    axis.units = 'µm'
                elif unit_str.lower() in ['ev', 'electron volt']:
                    axis.units = 'eV'
                else:
                    axis.units = unit_str
            else:
                axis.units = ''

        # Identify axis types based on position (after transpose, should be Y, X, Energy)
        if len(signal.axes_manager._axes) == 3:
            # Standard EELS: [Y, X, Energy]
            signal.axes_manager._axes[0].name = 'Y'
            signal.axes_manager._axes[1].name = 'X'
            signal.axes_manager._axes[2].name = 'Energy Loss'

            # If last axis doesn't have units, assume eV
            if not signal.axes_manager._axes[2].units:
                signal.axes_manager._axes[2].units = 'eV'

            # Update navigation/signal axes
            signal.axes_manager._navigation_axes = signal.axes_manager._axes[:2]
            signal.axes_manager._signal_axes = [signal.axes_manager._axes[2]]

        print(f"Loaded with ncempy:")
        for i, ax in enumerate(signal.axes_manager._axes):
            print(f"  Axis {i} ({ax.name}): scale={ax.scale:.4f} {ax.units}, offset={ax.offset:.4f}")

        return signal

    except ImportError:
        print("ncempy not available, trying hyperspy...")
    except Exception as e:
        print(f"ncempy failed: {e}, trying hyperspy...")
        import traceback
        traceback.print_exc()

    # Try hyperspy as fallback
    try:
        import hyperspy.api as hs

        hs_signal = hs.load(filepath)

        if isinstance(hs_signal, list):
            hs_signal = hs_signal[0]

        # Convert to our Signal1D
        signal = Signal1D(hs_signal.data)

        # Copy axis calibration
        if hasattr(hs_signal, 'axes_manager'):
            for i, hs_axis in enumerate(hs_signal.axes_manager._axes):
                if i < len(signal.axes_manager._axes):
                    signal.axes_manager._axes[i].scale = hs_axis.scale
                    signal.axes_manager._axes[i].offset = hs_axis.offset
                    signal.axes_manager._axes[i].units = hs_axis.units
                    signal.axes_manager._axes[i].name = hs_axis.name

            # Copy navigation/signal axes designation
            signal.axes_manager._navigation_axes = []
            signal.axes_manager._signal_axes = []

            for hs_ax in hs_signal.axes_manager.navigation_axes:
                idx = hs_signal.axes_manager._axes.index(hs_ax)
                if idx < len(signal.axes_manager._axes):
                    signal.axes_manager._navigation_axes.append(signal.axes_manager._axes[idx])

            for hs_ax in hs_signal.axes_manager.signal_axes:
                idx = hs_signal.axes_manager._axes.index(hs_ax)
                if idx < len(signal.axes_manager._axes):
                    signal.axes_manager._signal_axes.append(signal.axes_manager._axes[idx])

        print(f"Loaded with hyperspy:")
        for i, ax in enumerate(signal.axes_manager._axes):
            print(f"  Axis {i} ({ax.name}): scale={ax.scale:.4f} {ax.units}, offset={ax.offset:.4f}")

        return signal

    except ImportError:
        print("hyperspy not available")
    except Exception as e:
        print(f"hyperspy failed: {e}")
        import traceback
        traceback.print_exc()

    raise IOError(f"Could not load DM3/DM4 file. Install 'ncempy' or 'hyperspy': pip install ncempy")


# =============================================================================
# HDF5 EELS DATA READER
# =============================================================================

def load_hdf5_eels(filepath: str) -> Signal1D:
    """
    Load EELS data from HDF5 file.

    Parameters
    ----------
    filepath : str
        Path to HDF5 file

    Returns
    -------
    Signal1D
        EELS signal object
    """
    import h5py

    with h5py.File(filepath, 'r') as f:
        # Common HDF5 structures for EELS data
        data_paths = [
            'EELS/data', 'eels/data', 'Data/data',
            'Experiments/EELS/data', 'entry/data/data',
            'spectrum', 'data', 'counts', 'intensity'
        ]

        energy_paths = [
            'EELS/energy', 'eels/energy', 'Data/energy',
            'Experiments/EELS/energy', 'entry/data/energy',
            'energy_loss', 'energy', 'axis', 'x'
        ]

        data = None
        energy_axis = None

        # Find data
        for path in data_paths:
            if path in f:
                data = np.array(f[path])
                break

        if data is None:
            # Try to find any 3D dataset
            def find_3d_dataset(name, obj):
                if isinstance(obj, h5py.Dataset) and len(obj.shape) == 3:
                    return obj

            f.visititems(lambda n, o: find_3d_dataset(n, o))

        if data is None:
            raise ValueError("No EELS data found in HDF5 file")

        # Find energy axis
        for path in energy_paths:
            if path in f:
                energy_axis = np.array(f[path])
                break

        # Read metadata
        metadata = {}
        if 'metadata' in f.attrs:
            for key, value in f.attrs.items():
                metadata[key] = value

    # Create signal
    signal = Signal1D(data)
    signal.metadata = metadata

    # Set up energy axis
    if energy_axis is not None and len(data.shape) >= 1:
        signal_axis_idx = len(signal.axes_manager) - 1
        axis = signal.axes_manager[signal_axis_idx]

        if len(energy_axis) > 1:
            axis.scale = float(energy_axis[1] - energy_axis[0])
            axis.offset = float(energy_axis[0])
        elif len(energy_axis) == len(data.shape[-1]):
            axis.scale = 1.0
            axis.offset = float(energy_axis[0])

        axis.units = 'eV'
        axis.name = 'Energy Loss'

    return signal


# =============================================================================
# GENERIC LOADER
# =============================================================================

def load_eels(filepath: str) -> Signal1D:
    """
    Load EELS data from various file formats.

    Supports:
    - DM3/DM4 (Digital Micrograph) - uses ncempy or hyperspy
    - HDF5

    Parameters
    ----------
    filepath : str
        Path to EELS file

    Returns
    -------
    Signal1D
        EELS signal object
    """
    import os

    ext = os.path.splitext(filepath)[1].lower()

    if ext in ['.dm3', '.dm4']:
        return load_dm3_dm4(filepath)

    elif ext in ['.hdf5', '.h5', '.hspy']:
        return load_hdf5_eels(filepath)

    else:
        raise ValueError(f"Unsupported file format: {ext}. Supported: .dm3, .dm4, .hdf5, .h5")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_eels_signal(data: np.ndarray,
                       energy_scale: float = 1.0,
                       energy_offset: float = 0.0,
                       energy_units: str = 'eV') -> Signal1D:
    """
    Create an EELS signal from numpy array with energy calibration.

    Parameters
    ----------
    data : np.ndarray
        EELS data (can be 1D spectrum or 3D spectrum image)
    energy_scale : float
        Energy scale (eV per channel)
    energy_offset : float
        Energy offset (eV)
    energy_units : str
        Energy units

    Returns
    -------
    Signal1D
        EELS signal object
    """
    signal = Signal1D(data)

    # Set up energy axis on last axis (signal axis)
    signal_axis_idx = len(signal.axes_manager) - 1
    axis = signal.axes_manager[signal_axis_idx]
    axis.scale = energy_scale
    axis.offset = energy_offset
    axis.units = energy_units
    axis.name = 'Energy Loss'

    return signal