# pmpm: pandoc markdown preview machine, a simple markdown previewer



_Forked from [flaport/smdv][forkedfrom] on 2020-05-01;
original copyright and license notices are preserved in [LICENSE](LICENSE) and the same [GNU General Public License v3.0][gpl3] applies to this repository;
[all changes][changes] are documented._



---



The idea behind pmpm is to offer a fast local rendered html-preview of [pandoc-flavoured markdown][pandocmarkdown] files.
Thus, pmpm differs from the more feature rich [smdv][smdv] in various ways:

* pmpm is rough around the edges
* 1 server in pmpm, 2 servers in smdv
* pmpm uses a local html preview file, dropping the extra flask server and smdv's support for navigating directories from within the browser
* pmpm __accepts new markdown content under a named pipe__ at `$XDG_RUNTIME_DIR/pmpm_pipe`, renders it using pandoc, and distributes the rendered markdown via a websocket server,
  thus increasing interoperability and avoiding the slower detour (PUT to flask -> websocket to renderer -> websocket to browser)
* pmpm strives to be flake8/pep8 compliant
* pmpm features [Pandoc's Markdown][pandocmarkdown] flavour (+emoji), which is more suitable for __academic writing__ (support for bib files and citations, latex math, ...)
* for __increased speed__, pmpm aims to make use of async where possible and implements a block-wise lru_cached pandoc-backed rendering threadpool
* renders dot-parse code blocks using viz.js
* for __increased speed__, pmpm's javascript updates only the changed blocks instead of re-setting the entire innerhtml
* pmpm implements an __auto-scroll-to-first-change__ feature for a better live preview experience
* hack to allow [vim-instant-markdown][vim] to pass along the path of the currently edited file to enable relative include of images
* neat html layout based on [killercup's css](https://gist.github.com/killercup/5917178)
* live preview for vim ([vim-instant-markdown][vim]) and kate is doable
and basically can be implemented for any editor by regularly piping the current markdown to pmpm
--- as a fallback, watch a file for changes using inotify and pipe it to pmpm upon changes to get preview-on-save

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



---



## Examples

Please consult pandoc's user guide
to read up on [Pandoc's Markdown](https://pandoc.org/MANUAL.html)
and a detailed exposition on the markdown flavour supported by pmpm.
Pandoc-flavoured markdown supports syntax
(math, footnotes, citations, sequentially numbered lists, ...)
beyond traditional markdown features
(lists, emphasis, strong emphasis, links, ...).
Most of the functionality carries over to pmpm.

### Math

``` markdown
One can define commands
\newcommand{\f}[1]{\widehat{\mathbf{f}}(#1)}
and use those in block math

$$
\f{a}
=
\int_\mathcal{X}\sqrt{a}\exp^{i\pi x}
$$

and inline $\mathsf{math}$.
```

### Citations

[Pandoc's Markdown: Citations](https://pandoc.org/MANUAL.html#citations)

``` markdown
Some ways to cite references include [@doe1999], @alice20, and [-@42137];
and supported are also things like

* [see @doe1999;@alice20],
* refer to @42137 [p. 42],
* [@doe1999{ii, A, D-Z}, with a suffix], and
* [@alice20, {pp. iv, vi-xi, (xv)-(xvii)} with suffix here].

End the document with your heading of choice for the reference list,
which will be added at the end of the document.

# References

---
# YAML meta block (anywhere in the md file, multiple blocks possible)

# .bib file (absolute path or relative to the md file)
bibliography: bib.bib
# pmpm can currently handle only 1 bib file (pandoc can generally handle more)

# whether citations are hyperlinked to bib entries (default: false)
link-citations: true

# citation styles -- local or remote csl files can be selected
# dozens of styles can be fonud at the the official repository
# https://github.com/citation-style-language/styles
# csl: https://raw.githubusercontent.com/citation-style-language/styles/master/apa-cv.csl
# default is a chicago author date style

# references can be ensured to be included in the reference list via
nocite: |
  @bob137, @pan
# or, for all entries in the bibliography, use
# nocite: |
#   @*
---
```



[changes]: https://github.com/flaport/smdv/compare/9ea3657...sweichwald:master
[forkedfrom]: https://github.com/flaport/smdv/tree/9ea36575eef5993624ffefa682083c792e645a3f
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[pandocmarkdown]: https://pandoc.org/MANUAL.html#pandocs-markdown
[smdv]: https://github.com/flaport/smdv/
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[vim]: https://github.com/sweichwald/vim-instant-markdown

