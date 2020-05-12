# pmpm: pandoc markdown preview machine, a simple markdown previewer



_Forked from [flaport/smdv][forkedfrom] on 2020-05-01;
original copyright and license notices are preserved in [LICENSE](LICENSE)
and the same [GNU General Public License v3.0][gpl3] applies to this repository;
[all changes][changes] are documented._



---



The idea behind pmpm is to offer a fast local rendered html-preview of [pandoc-flavoured markdown][pandocmarkdown] files.\
__pmpm features the following__ (_and differs from [smdv][smdv] in various ways_)__:__

* pmpm features [Pandoc's Markdown][pandocmarkdown] flavour (+emoji)
  and is built upon [Pandoc][pandoc],
  which is more __suitable for academic writing__
  (with support for bib files and citations, latex math, ... also see [this article](academicwriting))
  and the flavoured markdown files can, using [Pandoc][pandoc], be converted to numerous formats (PDF, LaTeX, ...)
  and thus help boostrap the writing process
* for __ease of use and increased interoperability__,
  pmpm simply __accepts new markdown content under a named pipe__
  and quickly renders and distributes it for preview:\
  A simple `cat somefile.md > $XDG_RUNTIME_DIR/pmpm_pipe` and the preview is ready!\
  (_avoiding the slower detour:
  PUT to flask -> via websocket to renderer -> via websocket to browser_)
* pmpm implements an __auto-scroll-to-first-change__ feature for a better live preview experience
* __live preview__ for vim ([vim2pmpm][vim]) and kate is doable
and basically can be implemented for any editor by regularly piping the current markdown to pmpm
--- as a fallback, watch a file for changes using inotify and pipe it to pmpm upon changes to get preview-on-save
* to enable relative paths for images,
  the path of the currently edited file can be passed along to pmpm
  by adding a first line `<!-- filepath: /the/path/to/this.md -->`
  ([vim2pmpm][vim] does this automatically)
* for __increased speed__,
  pmpm aims to make use of async where possible
  and implements a block-wise lru_cached pandoc-backed rendering threadpool
* for __increased speed__, pmpm's javascript updates only the changed blocks instead of re-setting the entire innerhtml
* pmpm's default html layout is based on [killercup's css](https://gist.github.com/killercup/5917178)
  and looks nice
   -- __building your own theme__ is as simple as copying `pmpm.html` and `pmpm.css`,
  adapting to your liking, and firing up your new html file in the browser
* pmpm uses a localhost websocket server and a local html file\
  (_dropping the additional flask server that smdv uses
  comes at the loss of
  smdv's support for navigating directories from within the browser_)
* pmpm strives to be flake8/pep8 compliant
* renders dot-parse code blocks using viz.js

Thus, pmpm should be faster for its main usecase as a previewer
yet less feature-rich than smdv
-- and it features [Pandoc's Markdown][pandocmarkdown]! :sunglasses:



---



## Installation

Requires a reasonably recent pandoc, pandoc-citeproc, and browser.
Install pmpm using `pip install git+https://github.com/sweichwald/pmpm.git#egg=pmpm`.
If installed within a virtual environment, ensure that pmpm is appropriately linked and available on your path.

## Usage

* start the server `pmpm --start`\
  (use firefox with mathml support or add the option `--math katex`)
* open the `pmpm.html` file in your browser
* pipe some markdown to pmpm `cat file.md > $XDG_RUNTIME_DIR/pmpm_pipe`\
  (possibly passing along the filepath via a first line html comment of the form `<!-- filepath:/dir/to/file.md -->` to enable relative image paths etc.)
* your browser should show the rendered markdown

For configuration options consult `pmpm --help`; configuration is also possible via environment variables with name pattern `PMPM_DEFAULT_[ARG]`.

Use in conjunction with [vim2pmpm][vim] to preview pandoc markdown in the browser while editing in vim.



---



**Ideas & TODOs:**

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



[academicwriting]: https://programminghistorian.org/en/lessons/sustainable-authorship-in-plain-text-using-pandoc-and-markdown
[changes]: https://github.com/flaport/smdv/compare/9ea3657...sweichwald:master
[forkedfrom]: https://github.com/flaport/smdv/tree/9ea36575eef5993624ffefa682083c792e645a3f
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[pandoc]: https://pandoc.org/
[pandocmarkdown]: https://pandoc.org/MANUAL.html#pandocs-markdown
[smdv]: https://github.com/flaport/smdv/
[vim]: https://github.com/sweichwald/vim2pmpm

