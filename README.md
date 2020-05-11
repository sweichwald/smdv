# pmpm: pandoc markdown preview machine, a simple markdown previewer



_Forked from [flaport/smdv][forkedfrom] on 2020-05-01;
original copyright and license notices are preserved in [LICENSE](LICENSE) and the same [GNU General Public License v3.0][gpl3] applies to this repository;
[all changes][changes] are documented._



---



The idea behind pmpm is to offer a fast local preview of [pandoc-flavoured markdown][pandocmarkdown] files.
Thus, pmpm differs from the more feature rich [smdv][smdv] in various ways:

* pmpm is rough around the edges
* 1 server in pmpm, 2 in smdv
* pmpm uses a local html preview file, dropping the extra flask server and thus smdv's support for navigating directories from within the browser
* pmpm __accepts new content under a named pipe__ at `$XDG_RUNTIME_DIR/pmpm_pipe` and distributes the rendered markdown via a websocket server,
  thus increasing interoperability and yavoiding the slower detour (PUT to flask -> websocket to renderer -> websocket to browser)
* pmpm strives to be flake8/pep8 compliant
* pmpm relies on [Pandoc's Markdown][pandocmarkdown] flavour (+emoji), which is more suitable for __academic writing__
* for __increased speed__, pmpm aims to make use of async where possible and implements a block-wise lru_cached pandoc-backed rendering threadpool
* renders dot-parse code blocks using viz.js
* for __increased speed__, pmpm's javascript updates only the changed blocks instead of re-setting the entire innerhtml
* pmpm implements an __auto-scroll-to-first-change__ feature for a better live preview experience
* hack to allow [vim-instant-markdown][vim] to pass along the path of the currently edited file to enable relative include of images
* uses [killercup's css](https://gist.github.com/killercup/5917178)
* uses [gruvbox style](https://www.jonashietala.se/blog/2015/08/04/gruvbox_syntax_highlighting_for_pandoc/) syntax highlighting
* pmpm supports citations
* live preview for vim/kate is doable and basically should be doable for any editor for which regular piping to pmpm can be implemented --- as a fallback, watch a file for changes using inotify and pipe it to pmpm upon changes to get preview-on-save

> pmpm should thus be faster for its main usecases, but less feature rich than smdv



---



## Installation

Requires pandoc and pandoc-citeproc.
Install using `pip install git+https://github.com/sweichwald/pmpm.git#egg=pmpm`.
If installed within a virtual environment, ensure that pmpm is appropriately linked and available on your path.

## Usage

* start the server `pmpm --start`
* open the pmpm.html file in your browser
* pipe some markdown to pmpm `cat file.md > $XDG_RUNTIME_DIR/pmpm_pipe`\
  (possibly passing along the filepath via a first line html comment of the form
  `<!-- filepath:/dir/to/file.md -->` to enable relative image paths etc.)
* your browser should show the rendered markdown

For configuration options consult `pmpm --help`; configuration is also possible via environment variables with name pattern `PMPM_DEFAULT_[ARG]`.

Use in conjunction with [vim-instant-markdown][vim] to preview pandoc markdown in the browser while editing in vim.



---



**Ideas & TODOs:**

* fix blockwise rendering to not mess with footnotes
* improve the csl pandoc-citeproc style to link to the article's source url provided in the bibfile
* fade-out highlight changed content
* kate plugin?



[changes]: https://github.com/flaport/smdv/compare/9ea3657...sweichwald:master
[forkedfrom]: https://github.com/flaport/smdv/tree/9ea36575eef5993624ffefa682083c792e645a3f
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[pandocmarkdown]: https://pandoc.org/MANUAL.html#pandocs-markdown
[smdv]: https://github.com/flaport/smdv/
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[vim]: https://github.com/sweichwald/vim-instant-markdown

