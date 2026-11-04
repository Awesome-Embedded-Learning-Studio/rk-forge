# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.20)
project(rknpu_rk3588 VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
get_filename_component(RKNN_REPOSITORY_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(RKNN_SDK_INCLUDE "$ENV{RKNN_SDK_INCLUDE}" CACHE PATH "Directory containing the external rknn_api.h")
if(NOT RKNN_SDK_INCLUDE)
    set(RKNN_SDK_INCLUDE "${RKNN_REPOSITORY_ROOT}/reference/rk3588/external/rknpu2/runtime/RK3588/Linux/librknn_api/include")
endif()
if(NOT EXISTS "${RKNN_SDK_INCLUDE}/rknn_api.h")
    message(FATAL_ERROR "External SDK header missing: set -DRKNN_SDK_INCLUDE=/path/to/include")
endif()

option(RKNN_BUILD_TESTS "Build native regression tests from the runtime tests/ directory" OFF)
option(RKNN_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
set(RKNN_MODEL_DIR "${RKNN_REPOSITORY_ROOT}/.claude/rknn" CACHE PATH "External model corpus")
set(RKNN_SYNC_EVIDENCE "" CACHE PATH "Optional recorded-board-buffer evidence")
set(RKNN_TEST_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/tests" CACHE PATH "Regression test source directory")

add_library(rknpu_core OBJECT
    src/shell.cpp
    src/loader.cpp
    src/driver.cpp
    src/emitter.cpp
    src/tensor.cpp
    src/execution.cpp
)
target_compile_features(rknpu_core PUBLIC cxx_std_20)
set_target_properties(rknpu_core PROPERTIES CXX_EXTENSIONS OFF POSITION_INDEPENDENT_CODE ON)
target_include_directories(rknpu_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include" "${RKNN_SDK_INCLUDE}")
target_compile_options(rknpu_core PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
if(RKNN_ENABLE_SANITIZERS)
    target_compile_options(rknpu_core PUBLIC -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(rknpu_core INTERFACE -fsanitize=address,undefined)
endif()

add_library(rknnrt SHARED)
target_link_libraries(rknnrt PRIVATE rknpu_core)
add_library(rknpu::runtime ALIAS rknnrt)
install(TARGETS rknnrt LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}")
install(FILES LICENSE README.md DESTINATION "${CMAKE_INSTALL_DOCDIR}")

if(RKNN_BUILD_TESTS)
    if(CMAKE_CROSSCOMPILING)
        message(FATAL_ERROR "Native regressions require a host build; use a separate build directory")
    endif()
    enable_testing()
    add_subdirectory("${RKNN_TEST_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/regressions")
endif()

find_program(CLANG_FORMAT_EXECUTABLE NAMES clang-format clang-format-18 clang-format-19)
if(CLANG_FORMAT_EXECUTABLE)
    file(GLOB_RECURSE RKNN_FORMAT_FILES CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/include/*.h"
        "${RKNN_TEST_SOURCE_DIR}/native/*.cpp")
    set(RKNN_FORMAT_STYLE "--style=file:${CMAKE_CURRENT_SOURCE_DIR}/.clang-format")
    add_custom_target(format
        COMMAND "${CLANG_FORMAT_EXECUTABLE}" "${RKNN_FORMAT_STYLE}" -i ${RKNN_FORMAT_FILES}
        VERBATIM)
    add_custom_target(format-check
        COMMAND "${CLANG_FORMAT_EXECUTABLE}" "${RKNN_FORMAT_STYLE}" --dry-run --Werror ${RKNN_FORMAT_FILES}
        VERBATIM)
endif()
