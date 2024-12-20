import os
import fcntl
import array
import uctypes as ctypes

class SPI(object):
    # Constants scraped from <linux/spi/spidev.h>
    _SPI_CPHA                   = 0x1
    _SPI_CPOL                   = 0x2
    _SPI_LSB_FIRST              = 0x8
    _SPI_IOC_WR_MODE            = 0x40016b01
    _SPI_IOC_RD_MODE            = 0x80016b01
    _SPI_IOC_WR_baudrate_HZ    = 0x40046b04
    _SPI_IOC_RD_baudrate_HZ    = 0x80046b04
    _SPI_IOC_WR_BITS_PER_WORD   = 0x40016b03
    _SPI_IOC_RD_BITS_PER_WORD   = 0x80016b03
    _SPI_IOC_MESSAGE_1          = 0x40206b00

    desc = {
        'tx_buf': ctypes.UINT64 | 0,
        'rx_buf': ctypes.UINT64 | 8,
        'len': ctypes.UINT32 | 16,
        'speed_hz': ctypes.UINT32 | 20,
        'delay_usecs': ctypes.UINT16 | 24,
        'bits_per_word': ctypes.UINT8 | 26,
        'cs_change': ctypes.UINT8 | 27,
        'tx_nbits': ctypes.UINT8 | 28,
        'rx_nbits': ctypes.UINT8 | 28,
        'pad': ctypes.UINT16 | 30,
    }
    xfer_data = bytearray(32)

    def __init__(self, devpath, mode=0, baudrate=1000, bit_order="msb", bits_per_word=8, extra_flags=0):
        """Instantiate a SPI object and open the spidev device at the specified
        path with the specified SPI mode, max speed in hertz, and the defaults
        of "msb" bit order and 8 bits per word.

        Args:
            devpath (str): spidev device path.
            mode (int): SPI mode, can be 0, 1, 2, 3.
            baudrate (int, float): maximum speed in Hertz.
            bit_order (str): bit order, can be "msb" or "lsb".
            bits_per_word (int): bits per word.
            extra_flags (int): extra spidev flags to be bitwise-ORed with the SPI mode.

        Returns:
            SPI: SPI object.

        Raises:
            OSError: if an I/O or OS error occurs.
            TypeError: if `devpath`, `mode`, `baudrate`, `bit_order`, `bits_per_word`, or `extra_flags` types are invalid.
            ValueError: if `mode`, `bit_order`, `bits_per_word`, or `extra_flags` values are invalid.

        """
        self._fd = None
        self._devpath = None
        self._open(devpath, mode, baudrate, bit_order, bits_per_word, extra_flags)

    def __del__(self):
        self.close()

    def __enter__(self):
        pass

    def __exit__(self, t, value, traceback):
        self.close()

    def _open(self, devpath, mode, baudrate, bit_order, bits_per_word, extra_flags):
        if not isinstance(devpath, str):
            raise TypeError("Invalid devpath type, should be string.")
        elif not isinstance(mode, int):
            raise TypeError("Invalid mode type, should be integer.")
        elif not isinstance(baudrate, (int, float)):
            raise TypeError("Invalid baudrate type, should be integer or float.")
        elif not isinstance(bit_order, str):
            raise TypeError("Invalid bit_order type, should be string.")
        elif not isinstance(bits_per_word, int):
            raise TypeError("Invalid bits_per_word type, should be integer.")
        elif not isinstance(extra_flags, int):
            raise TypeError("Invalid extra_flags type, should be integer.")

        if mode not in [0, 1, 2, 3]:
            raise ValueError("Invalid mode, can be 0, 1, 2, 3.")
        elif bit_order.lower() not in ["msb", "lsb"]:
            raise ValueError("Invalid bit_order, can be \"msb\" or \"lsb\".")
        elif bits_per_word < 0 or bits_per_word > 255:
            raise ValueError("Invalid bits_per_word, must be 0-255.")
        elif extra_flags < 0 or extra_flags > 255:
            raise ValueError("Invalid extra_flags, must be 0-255.")

        # Open spidev
        try:
            self._fd = os.open(devpath, os.O_RDWR)
        except OSError as e:
            raise OSError("Opening SPI device: error")

        self._devpath = devpath

        bit_order = bit_order.lower()

        # Set mode, bit order, extra flags
        buf = array.array("B", [mode | (SPI._SPI_LSB_FIRST if bit_order == "lsb" else 0) | extra_flags])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_MODE, buf, True)
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Setting SPI mode: error")

        # Set max speed
        buf = array.array("I", [int(baudrate)])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_baudrate_HZ, buf, True)
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_baudrate_HZ, buf, True)
        except OSError as e:
            raise OSError("Setting SPI max speed: error")

        # Set bits per word
        buf = array.array("B", [bits_per_word])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_BITS_PER_WORD, buf, True)
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_BITS_PER_WORD, buf, True)
        except OSError as e:
            raise OSError("Setting SPI bits per word: error")

    # Methods

    def send_recv(self, data, recv=None):
        """Shift out `data` and return shifted in data.

        Args:
            data (bytes, bytearray, list): a byte array or list of 8-bit integers to shift out.

        Returns:
            bytes, bytearray, list: data shifted in.

        Raises:
            OSError: if an I/O or OS error occurs.
            TypeError: if `data` type is invalid.
            ValueError: if data is not valid bytes.

        """
        if not isinstance(data, (bytes, bytearray, list)):
            raise TypeError("Invalid data type, should be bytes, bytearray, or list.")

        # Create mutable array
        try:
            buf = array.array('B', data)
        except OverflowError:
            raise ValueError("Invalid data bytes.")

        buf_addr = ctypes.addressof(buf)
        buf_in = bytearray(len(buf))
        buf_in_addr = ctypes.addressof(buf_in)

        # Prepare transfer structure
        spi_xfer = ctypes.struct(ctypes.addressof(SPI.xfer_data), SPI.desc, ctypes.LITTLE_ENDIAN)
        spi_xfer.tx_buf = buf_addr
        spi_xfer.rx_buf = buf_in_addr
        spi_xfer.len = len(buf)

        # Transfer
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_MESSAGE_1, spi_xfer, True)
        except OSError as e:
            raise OSError("SPI transfer: error")

        if recv is not None:
            recv = bytearray(buf_in)
        else:
            # Return shifted out data with the same type as shifted in data
            if isinstance(data, bytes):
                return bytes(bytearray(buf_in))
            elif isinstance(data, bytearray):
                return bytearray(buf_in)
            elif isinstance(data, list):
                return buf_in.tolist()

    def deinit(self):
        """Deinit the spidev SPI device.

        Raises:
            OSError: if an I/O or OS error occurs.

        """
        if self._fd is None:
            return

        try:
            os.close(self._fd)
        except OSError as e:
            raise OSError("Closing SPI device: error")

        self._fd = None

    # Immutable properties

    @property
    def fd(self):
        """Get the file descriptor of the underlying spidev device.

        :type: int
        """
        return self._fd

    @property
    def devpath(self):
        """Get the device path of the underlying spidev device.

        :type: str
        """
        return self._devpath

    # Mutable properties

    def _get_mode(self):
        buf = array.array('B', [0])

        # Get mode
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Getting SPI mode: error")

        return buf[0] & 0x3

    def _set_mode(self, mode):
        if not isinstance(mode, int):
            raise TypeError("Invalid mode type, should be integer.")
        if mode not in [0, 1, 2, 3]:
            raise ValueError("Invalid mode, can be 0, 1, 2, 3.")

        # Read-modify-write mode, because the mode contains bits for other settings

        # Get mode
        buf = array.array('B', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Getting SPI mode: error")

        buf[0] = (buf[0] & ~(SPI._SPI_CPOL | SPI._SPI_CPHA)) | mode

        # Set mode
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_MODE, buf, False)
        except OSError as e:
            raise OSError("Setting SPI mode: error")

    mode = property(_get_mode, _set_mode)
    """Get or set the SPI mode. Can be 0, 1, 2, 3.

    Raises:
        OSError: if an I/O or OS error occurs.
        TypeError: if `mode` type is not int.
        ValueError: if `mode` value is invalid.

    :type: int
    """

    def _get_baudrate(self):
        # Get max speed
        buf = array.array('I', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_baudrate_HZ, buf, True)
        except OSError as e:
            raise OSError("Getting SPI max speed: error")

        return buf[0]

    def _set_baudrate(self, baudrate):
        if not isinstance(baudrate, (int, float)):
            raise TypeError("Invalid baudrate type, should be integer or float.")

        # Set max speed
        buf = array.array('I', [int(baudrate)])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_baudrate_HZ, buf, False)
        except OSError as e:
            raise OSError("Setting SPI max speed: error")

    baudrate = property(_get_baudrate, _set_baudrate)
    """Get or set the maximum speed in Hertz.

    Raises:
        OSError: if an I/O or OS error occurs.
        TypeError: if `baudrate` type is not int or float.

    :type: int, float
    """

    def _get_bit_order(self):
        # Get mode
        buf = array.array('B', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Getting SPI mode: error")

        if (buf[0] & SPI._SPI_LSB_FIRST) > 0:
            return "lsb"

        return "msb"

    def _set_bit_order(self, bit_order):
        if not isinstance(bit_order, str):
            raise TypeError("Invalid bit_order type, should be string.")
        elif bit_order.lower() not in ["msb", "lsb"]:
            raise ValueError("Invalid bit_order, can be \"msb\" or \"lsb\".")

        # Read-modify-write mode, because the mode contains bits for other settings

        # Get mode
        buf = array.array('B', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Getting SPI mode: error")

        bit_order = bit_order.lower()
        buf[0] = (buf[0] & ~SPI._SPI_LSB_FIRST) | (SPI._SPI_LSB_FIRST if bit_order == "lsb" else 0)

        # Set mode
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_MODE, buf, False)
        except OSError as e:
            raise OSError("Setting SPI mode: error")

    bit_order = property(_get_bit_order, _set_bit_order)
    """Get or set the SPI bit order. Can be "msb" or "lsb".

    Raises:
        OSError: if an I/O or OS error occurs.
        TypeError: if `bit_order` type is not str.
        ValueError: if `bit_order` value is invalid.

    :type: str
    """

    def _get_bits_per_word(self):
        # Get bits per word
        buf = array.array('B', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_BITS_PER_WORD, buf, True)
        except OSError as e:
            raise OSError("Getting SPI bits per word: error")

        return buf[0]

    def _set_bits_per_word(self, bits_per_word):
        if not isinstance(bits_per_word, int):
            raise TypeError("Invalid bits_per_word type, should be integer.")
        if bits_per_word < 0 or bits_per_word > 255:
            raise ValueError("Invalid bits_per_word, must be 0-255.")

        # Set bits per word
        buf = array.array('B', [bits_per_word])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_BITS_PER_WORD, buf, False)
        except OSError as e:
            raise OSError("Setting SPI bits per word: error")

    bits_per_word = property(_get_bits_per_word, _set_bits_per_word)
    """Get or set the SPI bits per word.

    Raises:
        OSError: if an I/O or OS error occurs.
        TypeError: if `bits_per_word` type is not int.
        ValueError: if `bits_per_word` value is invalid.

    :type: int
    """

    def _get_extra_flags(self):
        # Get mode
        buf = array.array('B', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Getting SPI mode: error")

        return buf[0] & ~(SPI._SPI_LSB_FIRST | SPI._SPI_CPHA | SPI._SPI_CPOL)

    def _set_extra_flags(self, extra_flags):
        if not isinstance(extra_flags, int):
            raise TypeError("Invalid extra_flags type, should be integer.")
        if extra_flags < 0 or extra_flags > 255:
            raise ValueError("Invalid extra_flags, must be 0-255.")

        # Read-modify-write mode, because the mode contains bits for other settings

        # Get mode
        buf = array.array('B', [0])
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_RD_MODE, buf, True)
        except OSError as e:
            raise OSError("Getting SPI mode: error")

        buf[0] = (buf[0] & (SPI._SPI_LSB_FIRST | SPI._SPI_CPHA | SPI._SPI_CPOL)) | extra_flags

        # Set mode
        try:
            fcntl.ioctl(self._fd, SPI._SPI_IOC_WR_MODE, buf, False)
        except OSError as e:
            raise OSError("Setting SPI mode: error")

    extra_flags = property(_get_extra_flags, _set_extra_flags)
    """Get or set the spidev extra flags. Extra flags are bitwise-ORed with the SPI mode.

    Raises:
        OSError: if an I/O or OS error occurs.
        TypeError: if `extra_flags` type is not int.
        ValueError: if `extra_flags` value is invalid.

    :type: int
    """

    # String representation

    def __str__(self):
        return "SPI (device=%s, fd=%d, mode=%s, baudrate=%d, bit_order=%s, bits_per_word=%d, extra_flags=0x%02x)" % (self.devpath, self.fd, self.mode, self.baudrate, self.bit_order, self.bits_per_word, self.extra_flags)

