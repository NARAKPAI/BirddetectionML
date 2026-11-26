set(CMAKE_HOST_SYSTEM "Darwin-25.6.0")
set(CMAKE_HOST_SYSTEM_NAME "Darwin")
set(CMAKE_HOST_SYSTEM_VERSION "25.6.0")
set(CMAKE_HOST_SYSTEM_PROCESSOR "arm64")

set(_CMAKE_INPUT_TOOLCHAIN_FILE [==[/Users/max/esp/esp-idf/tools/cmake/toolchain-esp32s3.cmake]==])
set(_CMAKE_SYSTEM_TOOLCHAIN_FILE "/Users/max/esp/esp-idf/tools/cmake/toolchain-esp32s3.cmake")
include("${_CMAKE_SYSTEM_TOOLCHAIN_FILE}")

set(CMAKE_SYSTEM "Generic")
set(CMAKE_SYSTEM_NAME "Generic")
set(CMAKE_SYSTEM_VERSION "")
set(CMAKE_SYSTEM_PROCESSOR "")

set(CMAKE_CROSSCOMPILING "TRUE")

set(CMAKE_SYSTEM_LOADED 1)
