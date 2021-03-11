// Viz and Katex are loaded dynamically on demand
function loadScript(src, integrity, crossOrigin)
{
    const script = document.createElement('script');
    if(integrity !== undefined)
        script.integrity = integrity;
    if(crossOrigin !== undefined)
        script.crossOrigin = crossOrigin;
    script.src = src;
    const promise = new Promise((resolve, reject) => {
        script.onload = resolve;
        script.onerror = reject;
    });
    document.head.append(script);
    return promise;
}

function loadStyle(src, integrity, crossOrigin)
{
    const style = document.createElement('link');
    style.rel = 'stylesheet';
    style.type = 'text/css';
    if(integrity !== undefined)
        style.integrity = integrity;
    if(crossOrigin !== undefined)
        style.crossOrigin = crossOrigin;
    style.href = src;
    const promise = new Promise((resolve, reject) => {
        style.onload = resolve;
        style.onerror = reject;
    });
    document.head.append(style);
    return promise;
}


let _vizLoaded = false;
let _vizLoadPromise;
async function getViz() {
    if(!_vizLoaded) {
        if(_vizLoadPromise === undefined) {
            _vizLoadPromise = Promise.all([
                loadScript('./3rdparty/viz.js/2.1.2/viz.js'),
                loadScript('./3rdparty/viz.js/2.1.2/lite.render.js')
            ]);
        }
        await _vizLoadPromise;
        _vizLoaded = true;
    }

    return new Viz();
}

let _katex;
let _katexLoadPromise;
async function getKatex() {
    if(_katex === undefined) {
        if(_katexLoadPromise === undefined) {
            _katexLoadPromise = Promise.all([
                loadScript('./3rdparty/katex/0.13.0/katex.min.js'),
                loadStyle('./3rdparty/katex/0.13.0/katex.min.css')
            ]);
        }
        await _katexLoadPromise;
        _katex = katex;
    }
    return _katex;
}

// Table of contents
const tocContainer = document.getElementById('TOC');
const tocContent = document.getElementById('toc-content');
const tocTitle = document.getElementById('toc-title');
const tocTitleTextDefault = tocTitle?.textContent;
let tocEnabled = false;
let tocTitleText;
let tocUpdated = false;
let tocContentVisible = false;

function updateToc()
{
    // Remove current content
    tocContent.textContent = '';

    // Build toc based on headings
    // Use container.parentNode because this also includes references
    // Like pandoc's default 'toc-depth: 3'. Not configurable at the moment since
    // pandoc doesn't parse 'toc-depth' from YAML metadata block
    const hs = container.parentNode.querySelectorAll('h1, h2, h3');
    const uls = [tocContent];
    tocContent._pmpmLastHlevel = 1;
    let lastLi = undefined;
    for(const h of hs) {

        const hLevel = parseInt(h.nodeName[1]);
        if(hLevel == 1) {
            // Don't show the "Title" in the <header>
            if(h.classList.contains('title') && h.parentNode.nodeName == 'HEADER')
                continue;
            // Don't show the References header if the references are hidden
            // (either because no references exist or because a custom div is in the text)
            if(h.id === 'bibliography' && references.style.display === 'none')
                continue;
        }

        const lastHLevel = uls[uls.length-1]._pmpmLastHlevel;

        let ul;
        if(hLevel > lastHLevel && lastLi) {
            // Jump at most one level up, even if one level was left out
            // e.g. "# one\n### three"
            ul = document.createElement('ul');
            lastLi.appendChild(ul);
            uls.push(ul);
        } else if(hLevel < lastHLevel) {
            // Jump down to the lowest ul with _pmpmLastHlevel >= hLevel
            ul = uls[uls.length-1];
            while(uls.length > 1 && uls[uls.length-2]._pmpmLastHlevel >= hLevel) {
                uls.pop();
                ul = uls[uls.length-1];
            }
        } else {
            ul = uls[uls.length-1];
        }

        // Each ul has a "hLevel" which is that from the last added <li>
        ul._pmpmLastHlevel = hLevel;

        const a = document.createElement('a');
        // cloneNode so that math works also in toc
        for(const el of h.childNodes)
            a.appendChild(el.cloneNode(true));
        a.href = '#';
        a._pmpmNodeLink = h;
        a.onclick = nodeLinkClickEvent;

        const li = document.createElement('li');
        li.appendChild(a);

        ul.appendChild(li);

        lastLi = li;
    }
}

function toggleToc()
{
    if(!tocContentVisible) {
        tocContentVisible = true;
        if(!tocUpdated) {
            updateToc();
            tocUpdated = true;
        }
        tocContainer.classList.add('open');
        tocContent.style.display = 'block';
    } else {
        tocContentVisible = false;
        tocContent.style.display = 'none';
        tocContainer.classList.remove('open');
    }
}

// global variables
const status = document.getElementById('status');
const container = document.getElementById('content');
const children = container.children;
const hashAttr = 'data-hash';
const footnotes = document.getElementById('footnotes');
const footnotesChildren = footnotes.children;
const references = document.getElementById('references');
const referencesTitle = document.getElementById('bibliography');
let wrappingTagName = 'div';
let fpathLoadMessagePrefix = 'filepath:';
let contentBibid;
let citeprocBibid;
let suppressBibliography = false;
let fpath, port;
({fpath, port} = (() => {
    const tmp = new URLSearchParams(window.location.search);
    return {fpath: tmp.get('filepath'), port: tmp.get('port') ?? '9877'}
})());


// body
async function renderBlockContentsAsync(el)
{
    const promises = [];

    // Render katex
    for(const mathEl of el.getElementsByClassName('math')) {
        const latexStr = mathEl.textContent;
        promises.push(getKatex().then(katex => {
            try {
                katex.render(latexStr, mathEl, {
                    displayMode: mathEl.classList.contains('display')
                });
            } catch(e) {
                const errEl = document.createElement('span');
                errEl.style.color = 'red';
                errEl.textContent = latexStr + ' ('+e.message+')';
                mathEl.appendChild(errEl);
            }
        }));
    }

    // Render viz
    for(const vizEl of el.getElementsByClassName('dot-parse')) {
        promises.push(getViz().then(viz => {
            return viz.renderString(el.textContent, {engine: 'dot', format:'svg'});
        }).then(svg => {
            el.innerHTML = svg;
        }));
    }

    return Promise.all(promises);
}

function swapElements(parent, obj1, obj2) {
    // save the location of obj2
    const next2 = obj2.nextSibling;
    // special case for obj1 is the next sibling of obj2
    if (next2 === obj1) {
        // just put obj1 before obj2
        parent.insertBefore(obj1, obj2);
    } else {
        // insert obj2 right before obj1
        parent.insertBefore(obj2, obj1);

        // now insert obj1 where obj2 was
        if (next2) {
            // if there was an element after obj2, then insert obj1 right before that
            parent.insertBefore(obj1, next2);
        } else {
            // otherwise, just append as last child
            parent.appendChild(obj1);
        }
    }
}

function findFirstChangedChild(currentChildNodes, previousChildNodes)
{
    const nchildren = currentChildNodes.length;
    for(let i = 0; i < nchildren; i++) {
        const curChild = currentChildNodes[i];
        const prevChild = previousChildNodes[i];
        if(!prevChild)
            return curChild;
        if(!curChild.isEqualNode(prevChild)) {
            if(!curChild.childNodes.length)
                return curChild;
            else
                return findFirstChangedChild(curChild.childNodes, prevChild.childNodes);
        }
    }
    return currentChildNodes[nchildren-1];
}

function highlight(el)
{
    let origHasClass = el.hasAttribute('class');
    el.classList.add('highlight');
    setTimeout(() => {
        el.classList.add('fade');
        el.classList.remove('highlight');
        const func = () => {
            el.removeEventListener('transitionend', func);
            // reset transition and class attribute. otherwise the next
            // update will find this el in findFirstChangedChild()
            el.classList.remove('fade');
            if(!origHasClass)
                el.removeAttribute('class');
        };
        el.addEventListener('transitionend', func);
    }, 200);
}

function scrollToFirstChange(scrollTarget, scrollTargetCompare)
{
    // Find first actually changed element in the first changed block
    // Important for large blocks
    let rect;
    if(scrollTargetCompare && scrollTarget.childNodes.length) {
        scrollTarget = findFirstChangedChild(scrollTarget.childNodes, scrollTargetCompare.childNodes);
        // We can't scroll to text elements
        while(scrollTarget.nodeType != Node.ELEMENT_NODE)
            scrollTarget = scrollTarget.parentNode;
        // We can't scroll to hidden elements, or some <math> child nodes (at least in Chrome)
        rect = scrollTarget.getBoundingClientRect();
        while(!rect.height) {
            scrollTarget = scrollTarget.parentNode;
            rect = scrollTarget.getBoundingClientRect();
        }
    } else {
        rect = scrollTarget.getBoundingClientRect();
    }

    const windowheight20 = window.innerHeight / 5;
    const newpos = rect.top + window.pageYOffset - windowheight20;

    // highlight
    // only highlight if scrolling more than 80% / 40% down / up
    // not on initial page load, if we start scrolled down
    const shouldHighlight = scrollTargetCompare &&
        (newpos - window.pageYOffset > 4 * windowheight20
         || newpos - window.pageYOffset < - 2 * windowheight20);
    if (shouldHighlight)
        highlight(scrollTarget);

    // scroll
    window.scrollTo({top: newpos});
}

// Load local links to .md files directly in this pmpm instance
// called for local src/href attributes, see websocket.py
function localLinkClickEvent(el)
{
    if(el.tagName != 'A')
        return true;

    const newFullFpath = el.href.slice(7);
    if(!newFullFpath.endsWith('.md'))
        return true;

    getWebsocket().then((websocket) => websocket.send(fpathLoadMessagePrefix + newFullFpath));
    return false;
}

function nodeLinkClickEvent(event)
{
    let a = event.target;
    while(a && a.tagName != 'A')
        a = a.parentNode;
    if(!a)
        return true;

    // Push state so browser back button jumps to previous position
    history.pushState(history.state, fpath);
    window.scrollTo({top: a._pmpmNodeLink.getBoundingClientRect().top + window.pageYOffset});
    return false;
}

function extractFootnotes(newEl, newFn)
{
    // Check for section with class 'footnotes'
    let fn = newEl.firstElementChild;
    while(fn && !fn.classList.contains('footnotes'))
        fn = fn.nextElementSibling;
    if(!fn)
        return;

    // Check for ol
    let ol = fn.firstElementChild;
    while(ol && ol.tagName != 'OL')
        ol = ol.nextElementSibling;
    if(!ol)
        return;

    // Move each footnote to global footnotes
    let li;
    while(li = ol.firstElementChild) {
        const num = li.id.slice(2);

        // Fix link hrefs and ids
        // Do not set special ids and hrefs. Otherwise, the automatic
        // change detection in findFirstChangedChild() may just always
        // detect the first footnote.
        // But: attributes like _footenoteHref and _footnoteAref
        // are ignored by isEqualNode(), so we use them and do
        // scrolling in our own onclick event handler.
        //
        // Also let CSS counters do the numbering
        // Then we don't have to manually renumber everything when we
        // update blocks in a different order than the display order
        li.removeAttribute('id'); // not unique
        for(const aback of li.getElementsByTagName('a')) {
            if(aback.getAttribute('href') == '#fnref'+num) {
                const aref = document.getElementById('fnref'+num);
                aref.removeAttribute('id'); // not unique
                aref._pmpmNodeLink = aback;
                aref.onclick = nodeLinkClickEvent;

                // Remove number in the <sup> inside the link
                // CSS counters should do the numbering
                aref.firstElementChild.textContent = '';

                li._footnoteAref = aref;
                aback._pmpmNodeLink = aref;
                aback.onclick = nodeLinkClickEvent;

                break; // Should only be one such link
            }
        }

        // Move footnote to global footnotes
        ol.removeChild(li);
        newFn.appendChild(li);
    }

    // Remove footnotes container
    newEl.removeChild(fn);
}

function extractReferences(newEl)
{
    const referenceElements = [];

    for(const el of newEl.getElementsByClassName('citation')) {
        const citekeys = el.getAttribute('data-cites').split(' ');
        const textcite = el.textContent;

        // Save textcite for later.
        el._referenceTextcite = textcite;

        // If we know this textcite's html, directly use it
        // Otherwise, we have to request it from the websocket
        // In any case, push this element into the textcitesCache
        const cache = _textcitesCache[textcite];
        if(cache === undefined) {
            _textcitesCache[textcite] = {elements: [el]};
            // Visually indicate that this textcite is being fetched
            el.classList.add('loading');
        } else {
            cache.elements.push(el);
            if(cache.html !== undefined) {
                el.innerHTML = cache.html;
            } else {
                // Visually indicate that this textcite is being fetched
                el.classList.add('loading');
            }
        }

        referenceElements.push(el);
    }

    // Save all reference elements.
    newEl._referenceElements = referenceElements;
}

function replaceRefList(refList)
{
    // Remove old references element, if any
    if(_refsElement !== undefined && _refsElement !== refList)
        _refsElement.parentNode.removeChild(_refsElement);
    _refsElement = refList;

    // Insert in correct place
    const refs = document.getElementById('refs');
    if(refs)
        refs.appendChild(refList);
    else
        references.appendChild(refList);
}

function showHideRefList()
{
    if(_refsElement !== undefined) {
        // If a references list exists, show/hide it
        const hide = suppressBibliography || contentBibid === null;
        _refsElement.style.display = hide ? 'none' : 'block';
        // Separately hide the references section at the bottom.
        // Hide this also if the references list is in a custom <div id="refs"></div>
        // Otherwise, a possible references title will still be shown
        references.style.display = hide || _refsElement.parentNode !== references  ? 'none' : 'block';
    } else {
        // If no references list exists, hide the references section at the bottom
        // This is to also hide a possible references title
        references.style.display = 'none';
    }
}

function updateRefsFromCiteprocResult()
{
    // Save bibid of bibid that is used now
    citeprocBibid = _lastCiteprocBibid;

    // parse the HTML in a temporary container
    const div = document.createElement('div');
    div.innerHTML = _lastCiteprocHtml;

    // Update textcites
    let i = 0;
    const updatedTextcites = {};
    const citeprocCitations = div.getElementsByClassName('citation');
    for(const block of children) {
        const referenceElements = block._referenceElements;
        if(referenceElements === undefined)
            continue;
        for(const el of referenceElements) {
            i++;
            const textcite = el._referenceTextcite;
            if(updatedTextcites[textcite])
                continue;
            updatedTextcites[textcite] = true;

            // Update all citations with the same textcite with new html, if HTML has changed
            const citeprocCitation = citeprocCitations[i-1];
            const textciteCache = _textcitesCache[textcite];

            // For pandoc version < 2.11:
            // Not-found citations are displayed as "???" by default, replace with citekey
            // Must be done before html compare
            // For pandoc version >= 2.11:
            // This doesn't work because not-found citations don't have "citeproc-not-found" class.
            // But: Not-found citations already contain the citekey anyway.
            // Note: For pandoc version >= 2.11 the following for loop is redundant,
            // yet should have no noticeable effect on performance;
            // if performance should be a problem in the future: have the server send along
            // a flag indicating whether the client is required to replace  not-found citation keys
            for(const missing of citeprocCitation.getElementsByClassName('citeproc-not-found'))
                missing.textContent = missing.getAttribute('data-reference-id');

            const html = citeprocCitation.innerHTML;
            if(textciteCache.html == html)
                continue;
            textciteCache.html = html;
            for(const tmp of textciteCache.elements) {
                tmp.innerHTML = html;
                // Remove visual indication as this textcite has been fetched successfully
                tmp.classList.remove('loading');
            }
        }
    }

    // Replace reference list with new reference list, if any
    const refList = div.querySelector('.references');
    if(refList) {
        refList.id = 'pmpmRefs'; // avoid collision with custom <div id="refs">
        replaceRefList(refList);
        showHideRefList();
    }

    // Signal that rendering is finished
    if(_citeprocDoneResolve)
        _citeprocDoneResolve();
}

let _lastCiteprocHtml;
let _lastCiteprocBibid;
function citeprocResultEvent(html, bibid)
{
    if(bibid == _lastCiteprocBibid) {
        // We already have this
        return;
    }

    _lastCiteprocHtml = html;
    _lastCiteprocBibid = bibid;

    if(_lastCiteprocBibid == contentBibid) {
        // Citeproc result is for htmlblocks that we have already loaded
        updateRefsFromCiteprocResult();
    } else {
        // Citeproc result is for htmlblocks that is either already gone or not yet loaded
        // Thus, delay/skip for now.
    }
}

const _textcitesCache = {};
let _refsElement;
let _citeprocDoneResolve;
let _citeprocDoneReject;
let _numberFootnotes = 0;
function updateBodyFromBlocks(contentnew, referenceSectionTitle)
{
    // Go through new content blocks. At each step we ensure that <div id="content"> matches the new contents up to block i
    let i;
    let firstChange;
    let firstChangeCompare;
    const renderPromises = [];
    for(i = 0; i < contentnew.length; i++) {

        const newhash = contentnew[i][0];

        // Check if node with hash of new block already exists
        // If it exists: Take it and move it to position i if needed
        // If it doesn't exist: Create it and insert it
        // Only check at position >= i so that we don't move away nodes we already put at positions < i
        // This is important if multiple content elements with the same hash exist
        let j;
        for(j = i; j < children.length && children[j].getAttribute(hashAttr) != newhash; j++);
        if(j < children.length) {
            // Hash does exist -- at position j
            if(j != i) {
                // Swap content blocks elements i and j
                swapElements(container, children[j], children[i]);

                // Swap footnotes blocks i and j if necessary, i.e. if any contains footnotes
                if(footnotesChildren[j].childElementCount || footnotesChildren[i].childElementCount)
                    swapElements(footnotes, footnotesChildren[j], footnotesChildren[i]);

                if (firstChange === undefined) {
                    firstChange = children[i];
                    firstChangeCompare = children[j];
                }
            }
        } else {
            // Hash does not exist, creating new
            const newEl = document.createElement(wrappingTagName);
            newEl.setAttribute(hashAttr, newhash);
            newEl.innerHTML = contentnew[i][1];
            container.insertBefore(newEl, children[i]);

            // Create footnotes placeholder
            const newFn = document.createElement('ol');
            footnotes.insertBefore(newFn, footnotesChildren[i]);

            // Check footnotes.
            extractFootnotes(newEl, newFn);
            _numberFootnotes += newFn.childElementCount;

            // Check references
            extractReferences(newEl);

            // asynchronously render latex and viz if necessary
            renderPromises.push(renderBlockContentsAsync(newEl));

            if (firstChange === undefined) {
                firstChange = children[i];
                firstChangeCompare = children[i+1];
            }
        }
    }

    // Now all non-needed elements from original content should be at the end and we can remove them
    while(children.length > i) {
        const block = container.lastElementChild;

        // Update references textcites cache
        // We do not remove elements form bibliography here. A new citeproc result will come anyway (or has come already)
        const referenceElements = block._referenceElements;
        if(referenceElements !== undefined) {
            for(const el of referenceElements) {
                // Remove refcounts from _textcitesCache
                const textcite = el._referenceTextcite;
                const cache = _textcitesCache[textcite];
                if(cache.elements.length == 1)
                    delete _textcitesCache[textcite];
                else {
                    // TODO: Maybe not optimal if there are many same textcites?
                    cache.elements = cache.elements.filter(e => e !== el);
                }
            }
        }

        // Remove block and footnote block
        container.removeChild(block);

        const fnBlock = footnotes.lastElementChild;
        _numberFootnotes -= fnBlock.childElementCount;
        footnotes.removeChild(fnBlock);
    }

    if (firstChange !== undefined) {
        // Show/hide footnotes
        footnotes.parentNode.style.display = _numberFootnotes > 0 ? 'block': 'none';

        if(_refsElement !== undefined) {
            // Check if
            // a) current reference list got removed from document
            //    Happens when custom <div id="refs"></div> is removed
            // b) current reference list is at bottom, but a custom <div id="refs'> just got added
            // In either case: Move _refsElement to new location
            if(!_refsElement.isConnected ||
                (_refsElement.parentNode === references && document.getElementById('refs')))
                replaceRefList(_refsElement);
        }
    }

    // Show/hide bibliography
    // Do before scrolling because this can change the scroll position for custom <div id="refs">
    // Do outside firstchange !== undefined check, because this can change without htmlblocks changes
    showHideRefList();

    // Show/hide toc container
    tocContainer?.style.setProperty('display', tocEnabled ? 'block' : 'none');

    const blockRenderingPromise = Promise.all(renderPromises);

    if(firstChange !== undefined) {
        blockRenderingPromise.finally(() => {
            // Update table of contents if toc is enabled and currently visible.
            // Otherwise, mark toc as to-be-updated when it becomes visible next time.
            // But only after rendering is finished. Otherwise katex in headings may not
            // be rendered yet and cannot be copied to toc.
            if(tocEnabled && tocContentVisible)
                updateToc();
            else
                tocUpdated = false;

            // scroll (first changed child of) first changed block into view
            // But only after rendering is finished. Otherwise the first change detection
            // may find a still-rendering but unchanged element.
            scrollToFirstChange(firstChange, firstChangeCompare);
        });
    } else {
        // Even if no html block is changed, we must update the toc if it
        // is visible and still has an old version.
        // Can happen e.g. if we start with toc visible, then get 'toc: false',
        // then change heading (so that toc is not directly updated),
        // then again get 'toc: true' (without changing any blocks)
        if(tocEnabled && tocContentVisible && !tocUpdated)
            updateToc();
    }

    // Set toc title
    if(tocEnabled)
        tocTitle.textContent = tocTitleText;

    // Set references title
    if(referenceSectionTitle !== "") {
        referencesTitle.textContent = referenceSectionTitle;
        referencesTitle.style.display = "";
    } else
        referencesTitle.style.display = "none";

    const citeprocRenderingPromise = new Promise((resolve, reject) => {
        _citeprocDoneResolve = resolve;
        _citeprocDoneReject = reject;
    });

    // We can immediately resolve the citeprocRenderingPromise, if
    // - citeproc is already correctly loaded since bibid is unchanged
    // - this is a document without any bibliography
    if(contentBibid == citeprocBibid || null === contentBibid)
        _citeprocDoneResolve();

    // If a citeproc response came in already for this content (before the htmlblocks!), apply it now
    if(contentBibid != citeprocBibid && _lastCiteprocBibid == contentBibid)
        updateRefsFromCiteprocResult();

    // After all is done, emit pmpmRenderingDone event
    // This is used in Kate plugin
    Promise.all([blockRenderingPromise, citeprocRenderingPromise]).then(() => {
        document.dispatchEvent(new Event('pmpmRenderingDone'));
    });
}

// websockets
function showStatusWarning(text)
{
    status.style.display = 'block';
    status.style.backgroundColor = '#bf0303';
    status.style.color = '#fefefe';
    status.textContent = text;
}

function showStatusInfo(text)
{
    status.style.display = 'block';
    status.style.backgroundColor = '#444';
    status.style.color = '#fefefe';
    status.textContent = text;
}

function hideStatus()
{
    status.style.display = 'none';
}

const websocketUrl = `ws://localhost:${port}/`;
let _websocket;
let _websocketResolve;
let _websocketPromise = new Promise((resolve, reject) => {
    _websocketResolve = resolve;
});
async function initWebsocket()
{
    showStatusInfo('Connecting to '+websocketUrl+'...');

    _websocket = new WebSocket(websocketUrl);
    _websocket.onopen = function() {
        hideStatus();
        _websocketResolve();
    };
    _websocket.onmessage = function (event) {
        // parse message
        const message = JSON.parse(event.data);

        if(message.htmlblocks !== undefined) {
            // update page
            tocEnabled = message.toc;
            tocTitleText = message["toc-title"] ?? tocTitleTextDefault;
            contentBibid = message.bibid;
            suppressBibliography = message["suppress-bibliography"];
            updateBodyFromBlocks(message.htmlblocks, message["reference-section-title"]);
        } else {
            if(message.bibid !== undefined) {
                // Async citeproc result
                citeprocResultEvent(message.html, message.bibid);
                return;
            }
            if(message.error !== undefined) {
                // backend error
                showStatusWarning(message.error);
                return;
            }
            if(message.status !== undefined) {
                // progressbar
                showStatusInfo(message.status);
                return;
            }

            // Shouldn't happen
            return;
        }

        // change browser url
        if (message.filepath != fpath) {
            const urlParams = new URLSearchParams({filepath: message.filepath});
            if(port != '9877')
                urlParams.set('port', port);
            fpath = message.filepath;
            window.document.title = 'pmpm - '+fpath;
            history.pushState({fpath:fpath}, fpath, '?'+urlParams);
        } else {
            history.replaceState({fpath:fpath}, fpath);
        }

        // hide status, if still shown from reconnect
        hideStatus();
    };

    _websocket.onclose = _websocket.onerror = function() {
        if(_websocket) {
            _websocketPromise = new Promise((resolve, reject) => {
                _websocketResolve = resolve;
            });
            _websocket = null;
            _websocketPromise.then(() => showStatusInfo('Just connected to '+websocketUrl+'. Shown content is possibly outdated. Pipe something to pmpm ;-)'));
            setTimeout(initWebsocket, 5000);
            showStatusWarning('Error connecting to '+websocketUrl+'. Retrying in 5 seconds...');
        }
    };
}

async function getWebsocket()
{
    await _websocketPromise;
    return _websocket;
}

window.onpopstate = function (event) {

    // Don't do anything on scroll to footnotes
    if(event.state === null)
        return;

    const newFpath = event.state.fpath;

    // Don't reload already open fpath when e.g. only scrolled back from footnotes
    if(newFpath == fpath)
        return;

    fpath = newFpath;
    window.document.title = 'pmpm - '+fpath;
    getWebsocket().then((websocket) => websocket.send(fpathLoadMessagePrefix + fpath));
};

function init(customWrappingTagName, customFpathLoadMessagePrefix)
{
    // Custom wrapping tag name, for slides
    if(customWrappingTagName !== undefined)
        wrappingTagName = customWrappingTagName;

    // Custom fpath load message prefix, for slides
    if(customFpathLoadMessagePrefix !== undefined)
        fpathLoadMessagePrefix = customFpathLoadMessagePrefix;

    // Load websocket
    initWebsocket();

    // Table of content toggle
    // Is ignored if no <div id="toc"> exists (e.g. revealjs)
    tocContainer?.getElementsByClassName('toc-toggle')[0]?.addEventListener('click', (ev) => {
        toggleToc();
        ev.preventDefault();
    });

    // Load initial document if any
    if(fpath && fpath !== 'LIVE') {
        window.document.title = 'pmpm - '+fpath;
        getWebsocket().then((websocket) => websocket.send(fpathLoadMessagePrefix + fpath));
    } else {
        // When refreshing the page, it may be irritatingly empty --> show this
        getWebsocket().then((_) => showStatusInfo('Just connected to '+websocketUrl+'. Pipe something to pmpm ;-)'));
    }
}


