**Work in Progress**

Forked from [flaport/smdv][forkedfrom] on 2020-05-01;
original copyright and license notices are preserved in [LICENSE](LICENSE) and the same [GNU General Public License v3.0][gpl3] applies to this repository;
[all changes][changes] are documented.

Some changes compared to the original:

* use [Pandoc's Markdown][pandocmarkdown] flavour (+emoji), which is more suitable for academic writing
* flake8/pep8 compliance
* change `@pipe`/`@put` to `live_pipe`/`live_put` for less special URIs
* separate the html template and css from the python file, strip smdv specific css (other than that for the navbar) and replace it by the default pandoc css
* implement a hacky rudimentary lru_cache-based speed-up
* renders dot-parse code blocks using viz.js
* hack to allow [vim-instant-markdown][vim] to pass along the path of the currently edited file to enable relative include of images
* [killercup's css](https://gist.github.com/killercup/5917178)
* [gruvbox style](https://www.jonashietala.se/blog/2015/08/04/gruvbox_syntax_highlighting_for_pandoc/) syntax highlighting

Ideas/TODOs:

* fix autoscroll to not mess with multiline blocks (equations, code, yaml) and enable scrolling to footnotes
* fix lru_cache-based rendering to not mess with compact vs loose lists, footnote and example list numbering, etc.
* bib support
* markdown preview for kate
* update syntax highlighting style, c.f. [here](https://www.jonashietala.se/blog/2019/01/25/site_restyle_and_update/#changes-to-code-display)
* trim down dropping support for/reference to neovim interaction



---



# smdv: a **s**imple **m**ark**d**own **v**iewer

Requires pandoc.
Install using `pip install git+https://github.com/sweichwald/smdv.git#egg=smdv`.
If installed within a virtual environment, ensure that smdv is appropriately linked and available on your path.

Use in conjunction with [vim-instant-markdown][vim] to preview pandoc markdown in the browser while editing in vim.

For configuration options consult `smdv --help`; configuration is also possible via environment variable `SMDV_DEFAULT_ARGS`.



[changes]: https://github.com/flaport/smdv/compare/9ea3657...sweichwald:master
[forkedfrom]: https://github.com/flaport/smdv/tree/9ea36575eef5993624ffefa682083c792e645a3f
[gpl3]: https://www.gnu.org/licenses/gpl-3.0.html
[pandocmarkdown]: https://pandoc.org/MANUAL.html#pandocs-markdown
[vim]: https://github.com/sweichwald/vim-instant-markdown
