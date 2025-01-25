#include <boost/decimal.hpp>

int main()
{
    using namespace boost::decimal;

    const decimal128 number = decimal128{1} / decimal128{97};

    const decimal32 d32_scientific{ number };
    const decimal64 d64_scientific{ number };
    const decimal128 d128_scientific{ number };
    const decimal32_fast df32_scientific{ number };
    const decimal64_fast df64_scientific{ number };
    const decimal128_fast df128_scientific{ number };

    const decimal32 factor{2468, 2};

    const decimal32 d32_fixed{ d32_scientific * factor };
    const decimal64 d64_fixed{ d64_scientific * factor };
    const decimal128 d128_fixed{ d128_scientific * factor };
    const decimal32_fast df32_fixed{ df32_scientific * factor };
    const decimal64_fast df64_fixed{ df64_scientific * factor };
    const decimal128_fast df128_fixed{ df128_scientific * factor };

break_here:
    return EXIT_SUCCESS;
}
