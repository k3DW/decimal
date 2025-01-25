#!/bin/bash

# https://github.com/dotnet/runtime/issues/90791#issuecomment-1684394378
clang++ -I ../include -O0 -g -glldb -D_GLIBCXX_DEBUG ../main.cpp
