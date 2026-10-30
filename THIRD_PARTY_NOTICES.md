# Third-party notices

## miniaudio

`miniaudio` 1.71 is MIT. Its decoder extension includes dr_mp3, dr_flac, and stb_vorbis, which are in the public domain. libsndfile is not included.

## cffi and pycparser

`cffi` 2.1.1 and `pycparser` 3.12 are MIT. miniaudio uses them to call its extension.

## NumPy

`numpy` 2.5.4 is BSD-3-Clause. Parts of the wheel are also under 0BSD, MIT, Zlib, and CC0-1.0. The license list shipped in the wheel is `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`.

### GCC runtime libraries bundled in the NumPy wheel

Some NumPy wheels include copies of the GCC runtime libraries `libgfortran` and `libquadmath`. Those libraries are covered by the GNU General Public License version 3 with the GCC Runtime Library Exception, version 3.1.

The exception lets a program compile against and link those libraries, and distribute the result, without the GPL applying to the rest of the program. That permission holds when the program is an independent work that uses the runtime as a library, and it does not hold for a work that is otherwise a derivative of the GCC runtime. The source for these libraries is the GNU Compiler Collection: <https://gcc.gnu.org/onlinedocs/libgfortran/> and <https://gcc.gnu.org/onlinedocs/libquadmath/>. The exception text is <https://www.gnu.org/licenses/gcc-exception-3.1.en.html>.
