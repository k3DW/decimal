file ./a.out
source ../extra/boost_decimal_printers.py

break main:break_here

# set logging enabled on

define print_decimal_scientific
print d32_scientific
print d64_scientific
print d128_scientific
print df32_scientific
print df64_scientific
print df128_scientific
end

define print_decimal_fixed
print d32_fixed
print d64_fixed
print d128_fixed
print df32_fixed
print df64_fixed
print df128_fixed
end

run