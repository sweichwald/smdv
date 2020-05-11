# pmpm: pandoc markdown preview machine, a simple markdown previewer

Forked from [flaport/smdv][forkedfrom] on 2020-05-01;
original copyright and license notices are preserved in [LICENSE](LICENSE) and the same [GNU General Public License v3.0][gpl3] applies to this repository;
[all changes][changes] are documented.

The idea behind pmpm is to offer a fast local preview of pandoc-flavoured markdown files.
Thus, pmpm differs from the more feature rich smdv in various ways:

* pmpm is rough around the edges
* 1 server in pmpm, 2 in smdv
* pmpm uses an entirely local html preview file, dropping the extra flask server and thus its support for navigating directories from within the browser
* pmpm accepts new content under a named pipe at `$XDG_RUNTIME_DIR/pmpm_pipe` distributing the rendered markdown via a websocket server,
  thus avoiding the slower detour (PUT to flask -> websocket to renderer -> websocket to browser) and increasing interoperability
* pmpm strives to be flake8/pep8 compliant
* pmpm relies on [Pandoc's Markdown][pandocmarkdown] flavour (+emoji), which is more suitable for academic writing
* pmpm aims to make use of async where possible and implements a block-wise lru_cached pandoc-backed rendering threadpool for increased speed
* renders dot-parse code blocks using viz.js
* pmpm's javascript updates only the changed blocks instead of re-setting the entire innerhtml
* pmpm implements an auto-scroll-to-first-change feature for a better live preview experience
* hack to allow [vim-instant-markdown][vim] to pass along the path of the currently edited file via `<!-- filepath:/dir/to/file.md -->` to enable relative include of images
* uses [killercup's css](https://gist.github.com/killercup/5917178)
* uses [gruvbox style](https://www.jonashietala.se/blog/2015/08/04/gruvbox_syntax_highlighting_for_pandoc/) syntax highlighting
* pmpm supports citations
* live preview for vim/kate is doable and basically should be doable for any editor for which regular piping to pmpm can be implemented --- as a fallback, watch a file for changes using inotify and pipe it to pmpm upon changes to get preview-on-save

pmpm should thus be faster, but less feature rich

**Ideas & TODOs:**

* fix blockwise rendering to not mess with footnotes
* update syntax highlighting style, c.f. [here](https://www.jonashietala.se/blog/2019/01/25/site_restyle_and_update/#changes-to-code-display)



---



## Installation

Requires pandoc and pandoc-citeproc.
Install using `pip install git+https://github.com/sweichwald/pmpm.git#egg=pmpm`.
If installed within a virtual environment, ensure that pmpm is appropriately linked and available on your path.

## Usage

* start the server `pmpm --start`
* open the pmpm.html file in your browser
* pipe some markdown to pmpm `cat file.md > $XDG_RUNTIME_DIR/pmpm_pipe`
* your browser should show the rendered markdown

For configuration options consult `pmpm --help`; configuration is also possible via environment variables with name pattern `PMPM_DEFAULT_[ARG]`.

Use in conjunction with [vim-instant-markdown][vim] to preview pandoc markdown in the browser while editing in vim.



[changes]: https://github.com/flaport/smdv/compare/9ea3657...sweichwald:master
[forkedfrom]: https://github.com/flaport/smdv/tree/9ea36575eef5993624ffefa682083c792e645a3f
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[pandocmarkdown]: https://pandoc.org/MANUAL.html#pandocs-markdown
[vim]: https://github.com/sweichwald/vim-instant-markdown
