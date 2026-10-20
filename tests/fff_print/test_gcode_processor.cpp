#include <catch2/catch_all.hpp>

#include "libslic3r/GCode/GCodeProcessor.hpp"

using namespace Slic3r;

TEST_CASE("Resetting a G-code result releases its print-sized buffers", "[GCodeProcessor][Regression]")
{
    GCodeProcessorResult result{};
    for (int cycle = 0; cycle < 2; ++cycle) {
        result.moves.reserve(1024);
        result.lines_ends.assign(1024, 100);
        REQUIRE(result.moves.capacity() >= 1024);
        REQUIRE(result.lines_ends.capacity() >= 1024);

        result.reset();
        CHECK(result.moves.empty());
        CHECK(result.moves.capacity() == 0);
        CHECK(result.lines_ends.empty());
        CHECK(result.lines_ends.capacity() == 0);
    }
}
