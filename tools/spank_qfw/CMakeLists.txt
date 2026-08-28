cmake_minimum_required(VERSION 3.15)
project(spank_qfw C)

find_path(SLURM_INCLUDE_DIR NAMES slurm/spank.h REQUIRED)

add_library(spank_qfw MODULE spank_qfw.c)
target_include_directories(spank_qfw PRIVATE "${SLURM_INCLUDE_DIR}")
target_compile_features(spank_qfw PRIVATE c_std_11)
target_compile_options(spank_qfw PRIVATE
	-Wall -Wextra -Werror -O2 -pedantic)
set_target_properties(spank_qfw PROPERTIES
	PREFIX ""
	SUFFIX ""
	OUTPUT_NAME "spank_qfw.so")
