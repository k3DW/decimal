# Copyright 2025 Braden Ganetsky
# Distributed under the Boost Software License, Version 1.0.
# https://www.boost.org/LICENSE_1_0.txt

import gdb.printing
import re

"""
For all the code below adapted from C++, the following simplifications are made.
* `BOOST_DECIMAL_FAST_MATH` is defined
* `fmt = chars_format::general`
* `precision = -1`
"""

assert gdb.lookup_type("int").sizeof == 4 # We can't use `std::int32_t`, so assert just to be safe

class BoostDecimalHelpers:
    class Int128:
        def __init__(self, high: int = 0, low: int = 0):
            self.high = high
            self.low = low

    UINT64_MAX = 0xffffffffffffffff

    d32_comb_11_mask = 0b0_11000_000000_0000000000_0000000000
    d32_comb_11_significand_bits = 0b0_00001_000000_0000000000_0000000000
    d32_comb_11_exp_bits = 0b0_00110_000000_0000000000_0000000000
    d32_comb_01_mask = 0b0_01000_000000_0000000000_0000000000
    d32_comb_10_mask = 0b0_10000_000000_0000000000_0000000000
    d32_comb_00_01_10_significand_bits = 0b0_00111_000000_0000000000_0000000000
    d32_significand_mask = 0b0_00000_000000_1111111111_1111111111
    d32_significand_bits = 20
    d32_exponent_mask = 0b0_00000_111111_0000000000_0000000000
    d32_exponent_bits = 6
    d32_sign_mask = 0b1_00000_000000_0000000000_0000000000

    d64_comb_11_mask = 0b0_11000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_comb_11_significand_bits = 0b0_00001_00000000_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_comb_11_exp_bits = 0b0_00110_00000000_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_comb_01_mask = 0b0_01000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_comb_10_mask = 0b0_10000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_comb_00_01_10_significand_bits = 0b0_00111_00000000_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_significand_mask = 0b0_00000_00000000_1111111111_1111111111_1111111111_1111111111_1111111111
    d64_significand_bits = 50
    d64_exponent_mask = 0b0_00000_11111111_0000000000_0000000000_0000000000_0000000000_0000000000
    d64_exponent_bits = 8
    d64_sign_mask = 0b1_00000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000

    d128_comb_11_mask = Int128(0b0_11000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)
    d128_comb_11_significand_bits = Int128(0b0_00001_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)
    d128_comb_11_exp_bits = Int128(0b0_00110_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)
    d128_comb_01_mask = Int128(0b0_01000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)
    d128_comb_10_mask = Int128(0b0_10000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)
    d128_comb_00_01_10_significand_bits = Int128(0b0_00111_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)
    d128_significand_mask = Int128(0b1111111111_1111111111_1111111111_1111111111_111111, UINT64_MAX)
    d128_significand_bits = 110
    d128_exponent_mask = Int128(0b0_00000_111111111111_0000000000_0000000000_0000000000_0000000000_000000, 0)
    d128_exponent_bits = 12
    d128_sign_mask = Int128(0b1_00000_00000000_0000000000_0000000000_0000000000_0000000000_0000000000, 0)

    __precision_vals = {32 : 7, 64 : 16, 128 : 34}
    def precision(bit_width: int) -> int:
        return BoostDecimalHelpers.__precision_vals[bit_width]

    __bias_vals = {32 : 101, 64 : 398, 128 : 6176}
    def bias(bit_width: int) -> int:
        return BoostDecimalHelpers.__bias_vals[bit_width]

    __max_significand = {
        32 : 9_999_999,
        64 : 9_999_999_999_999_999,
        128 : [Int128(0b1111111111_1111111111_1111111111_1111111111_111111, UINT64_MAX), Int128(542101086242752, 4003012203950112767)],
    }
    def max_significand(bit_width: int, is_fast: bool) -> int:
        val = BoostDecimalHelpers.__max_significand[bit_width]
        if bit_width == 128:
            val = val[is_fast]
            val = (2**64 * val.high) + val.low
        return val

    __signbit_funcs = {
        32 : (lambda bits: bits & BoostDecimalHelpers.d32_sign_mask),
        64 : (lambda bits: bits & BoostDecimalHelpers.d64_sign_mask),
        128 : (lambda bits: bits["high"] & BoostDecimalHelpers.d128_sign_mask.high),
    }
    def signbit(bits, bit_width) -> int:
        return BoostDecimalHelpers.__signbit_funcs[bit_width](bits)
    
    def full_significand(bits, bit_width) -> int:
        if bit_width == 32:
            significand : int = 0
            if (bits & BoostDecimalHelpers.d32_comb_11_mask) == BoostDecimalHelpers.d32_comb_11_mask:
                if (bits & BoostDecimalHelpers.d32_comb_11_significand_bits) == BoostDecimalHelpers.d32_comb_11_significand_bits:
                    significand = 0b1001_0000000000_0000000000
                else:
                    significand = 0b1000_0000000000_0000000000
            else:
                significand |= ((bits & BoostDecimalHelpers.d32_comb_00_01_10_significand_bits) >> BoostDecimalHelpers.d32_exponent_bits)
            significand |= (bits & BoostDecimalHelpers.d32_significand_mask)
            return significand
        elif bit_width == 64:
            significand : int = 0
            if (bits & BoostDecimalHelpers.d64_comb_11_mask) == BoostDecimalHelpers.d64_comb_11_mask:
                if (bits & BoostDecimalHelpers.d64_comb_11_significand_bits) == BoostDecimalHelpers.d64_comb_11_significand_bits:
                    significand = 0b1001_0000000000_0000000000_0000000000_0000000000_0000000000
                else:
                    significand = 0b1000_0000000000_0000000000_0000000000_0000000000_0000000000
            else:
                significand |= ((bits & BoostDecimalHelpers.d64_comb_00_01_10_significand_bits) >> BoostDecimalHelpers.d64_exponent_bits)
            significand |= (bits & BoostDecimalHelpers.d64_significand_mask)
            return significand
        elif bit_width == 128:
            significand = BoostDecimalHelpers.Int128()
            high = int(bits["high"])
            low = int(bits["low"])
            if (high & BoostDecimalHelpers.d128_comb_11_mask.high) == BoostDecimalHelpers.d128_comb_11_mask.high:
                if (high & BoostDecimalHelpers.d128_comb_11_significand_bits.high) == BoostDecimalHelpers.d128_comb_11_significand_bits.high:
                    significand = BoostDecimalHelpers.Int128(0b10010000000000000000000000000000000000000000000000, 0)
                else:
                    significand = BoostDecimalHelpers.Int128(0b10000000000000000000000000000000000000000000000000, 0)
            else:
                significand.high |= ((high & BoostDecimalHelpers.d128_comb_00_01_10_significand_bits.high) >> BoostDecimalHelpers.d128_exponent_bits)
            significand.high |= (high & BoostDecimalHelpers.d128_significand_mask.high)
            significand.low |= (low & BoostDecimalHelpers.d128_significand_mask.low)
            return (2**64 * significand.high) + significand.low

    def unbiased_exponent(bits, bit_width) -> int:
        if bit_width == 32:
            bits = int(bits)
            vals = {
                BoostDecimalHelpers.d32_comb_11_mask : ((bits & BoostDecimalHelpers.d32_comb_11_exp_bits) >> (BoostDecimalHelpers.d32_significand_bits + 1)),
                BoostDecimalHelpers.d32_comb_10_mask : 0b10000000,
                BoostDecimalHelpers.d32_comb_01_mask : 0b01000000,
            }
            expval : int = vals[bits & BoostDecimalHelpers.d32_comb_11_mask]
            expval |= ((bits & BoostDecimalHelpers.d32_exponent_mask) >> BoostDecimalHelpers.d32_significand_bits)
            return expval
        elif bit_width == 64:
            bits = int(bits)
            vals = {
                BoostDecimalHelpers.d64_comb_11_mask : ((bits & BoostDecimalHelpers.d64_comb_11_exp_bits) >> (BoostDecimalHelpers.d64_significand_bits + 1)),
                BoostDecimalHelpers.d64_comb_10_mask : 0b1000000000,
                BoostDecimalHelpers.d64_comb_01_mask : 0b0100000000,
            }
            expval : int = vals[bits & BoostDecimalHelpers.d64_comb_11_mask]
            expval |= ((bits & BoostDecimalHelpers.d64_exponent_mask) >> BoostDecimalHelpers.d64_significand_bits)
            return expval
        elif bit_width == 128:
            high = int(bits["high"])
            high_word_significand_bits = BoostDecimalHelpers.d128_significand_bits - 64
            vals = {
                BoostDecimalHelpers.d128_comb_11_mask.high : ((high & BoostDecimalHelpers.d128_comb_11_mask.high) >> (high_word_significand_bits + 1)),
                BoostDecimalHelpers.d128_comb_10_mask.high : 0b10000000000000,
                BoostDecimalHelpers.d128_comb_01_mask.high : 0b01000000000000,
            }
            expval : int = vals[high & BoostDecimalHelpers.d128_comb_11_mask.high]
            expval |= ((high & BoostDecimalHelpers.d128_exponent_mask.high) >> high_word_significand_bits)
            return expval

class BoostDecimalPrinter:
    def __init__(self, val):
        self.val = val
        the_type = f"{self.val.type.strip_typedefs()}"
        self.is_fast = the_type.endswith("_fast")
        self.bit_width = int(re.search("(\d+)", the_type).group(1))

    def isneg(self) -> bool:
        if self.is_fast:
            return bool(self.val["sign_"])
        else:
            return BoostDecimalHelpers.signbit(self.val["bits_"], self.bit_width) != 0

    def significand(self) -> int:
        if self.is_fast:
            significand = self.val["significand_"]
            if self.bit_width == 128:
                significand = (2**64 * int(significand["high"])) + int(significand["low"])
            return int(significand)
        else:
            return BoostDecimalHelpers.full_significand(self.val["bits_"], self.bit_width)

    def exponent(self) -> int:
        if self.is_fast:
            unbiased_exponent = self.val["exponent_"].cast(gdb.lookup_type("int")) # Should be `std::int32_t`
        else:
            unbiased_exponent = BoostDecimalHelpers.unbiased_exponent(self.val["bits_"], self.bit_width)
        return unbiased_exponent - BoostDecimalHelpers.bias(self.bit_width)

    def to_chars_scientific_impl(self) -> str:
        out : str = "-" if self.isneg() else ""

        significand = int(self.significand())
        exponent = int(self.exponent())

        if significand == 0 and exponent == 0:
            return f"{out}0.0e+00"

        # `boost::decimal::frexp10()` and `boost::decimal::detail::normalize`
        target_precision = BoostDecimalHelpers.precision(self.bit_width)
        significand_digits = len(str(significand))
        if significand_digits < target_precision:
            zeros_needed = target_precision - significand_digits
            significand *= 10**zeros_needed
            exponent -= zeros_needed
        elif significand_digits > target_precision:
            excess_digits = significand_digits - (target_precision + 1)
            significand //= 10**excess_digits
            def fenv_round(val):
                trailing_num = val % 10
                exp_delta : int = 0
                val //= 10
                exp_delta += 1
                if trailing_num >= 5:
                    val += 1
                if val > BoostDecimalHelpers.max_significand(self.bit_width, self.is_fast):
                    val //= 10
                    exp_delta += 1
                return exp_delta
            exponent += fenv_round(significand) + excess_digits

        significand_str = str(significand)
        exponent += len(significand_str) - 1

        out += significand_str[:1] + "." + significand_str[1:]
        while out[-1] == '0':
            out = out[:-1]
        if out[-1] == '.':
            out = out[:-1]
        out += "e"

        abs_exp = -exponent if exponent < 0 else exponent
        out += ("-" if exponent < 0 else "+")
        if abs_exp <= 9:
            out += "0"
        out += str(abs_exp)

        return out

    def to_string(self) -> str:
        return self.to_chars_scientific_impl()

def boost_decimal_build_pretty_printer():
    pp = gdb.printing.RegexpCollectionPrettyPrinter("boost_decimal")
    add_concrete_printer = lambda name, printer: pp.add_printer(name, f"^{name}$", printer)

    add_concrete_printer("boost::decimal::decimal32", BoostDecimalPrinter)
    add_concrete_printer("boost::decimal::decimal64", BoostDecimalPrinter)
    add_concrete_printer("boost::decimal::decimal128", BoostDecimalPrinter)

    add_concrete_printer("boost::decimal::decimal32_fast", BoostDecimalPrinter)
    add_concrete_printer("boost::decimal::decimal64_fast", BoostDecimalPrinter)
    add_concrete_printer("boost::decimal::decimal128_fast", BoostDecimalPrinter)

    return pp

gdb.printing.register_pretty_printer(gdb.current_objfile(), boost_decimal_build_pretty_printer())
