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
    style.integrity = integrity;
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
                loadScript('https://cdn.tutorialjinni.com/viz.js/2.1.2/viz.js'),
                loadScript('https://cdn.tutorialjinni.com/viz.js/2.1.2/lite.render.js')
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
                loadScript('https://cdn.jsdelivr.net/npm/katex@0.11.1/dist/katex.min.js', 'sha384-y23I5Q6l+B6vatafAwxRu/0oK/79VlbSz7Q9aiSZUvyWYIYsd+qj+o24G5ZU2zJz', 'anonymous'),
                loadStyle('https://cdn.jsdelivr.net/npm/katex@0.11.1/dist/katex.min.css', 'sha384-zB1R0rpPzHqg7Kpt0Aljp8JPLqbXI3bhnPWROx27a9N0Ll6ZP/+DiW/UqRcLbRjq', 'anonymous')
            ]);
        }
        await _katexLoadPromise;
        _katex = katex;
    }
    return _katex;
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
let suppressBibliography = false;
let fpath = (new URLSearchParams(window.location.search)).get('filepath');


// body
async function renderBlockContentsAsync(el)
{
    // Render katex
    for(const mathEl of el.getElementsByClassName('math')) {
        const latexStr = mathEl.textContent;
        try {
            const katex = await getKatex();
            katex.render(latexStr, mathEl, {
                displayMode: mathEl.classList.contains('display')
            });
        } catch(e) {
            const errEl = document.createElement('span');
            errEl.style.color = 'red';
            errEl.textContent = latexStr + ' ('+e.message+')';
            mathEl.appendChild(errEl);
        }
    }

    // Render viz
    for(const vizEl of el.getElementsByClassName('dot-parse')) {
        const viz = await getViz();
        viz.renderString(el.textContent, {engine: 'dot', format:'svg'}).then(svg => el.innerHTML = svg);
    }
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

function scrollToFirstChange(scrollTarget, scrollTargetCompare)
{
    if(scrollTargetCompare && scrollTarget.childNodes.length) {
        // TODO: Delay until async katex / viz rendering is done?
        scrollTarget = findFirstChangedChild(scrollTarget.childNodes, scrollTargetCompare.childNodes);
        if(scrollTarget.nodeType != Node.ELEMENT_NODE)
            scrollTarget = scrollTarget.parentNode;
    }

    const windowheight20 = window.innerHeight / 5;
    const newpos = scrollTarget.getBoundingClientRect().top +
                      window.pageYOffset - windowheight20;

    // highlight
    // only highlight if scrolling more than 80% / 40% down / up
    // not on initial page load, if we start scrolled down
    const highlight = scrollTargetCompare &&
        (newpos - window.pageYOffset > 4 * windowheight20
         || newpos - window.pageYOffset < - 2 * windowheight20);
    let origBg, origHasStyleAttribute;
    if (highlight) {
        origBg = scrollTarget.style.background;
        origHasStyleAttribute = scrollTarget.hasAttribute('style');
        scrollTarget.style.background = "#fdf6e3";
    }

    // scroll
    window.scrollTo({top: newpos});

    // fade
    if (highlight) {
        scrollTarget.style.background = origBg;
        scrollTarget.style.transition = "background-color .573s linear";
        // reset transition and style attribute. otherwise the next update will find the same
        // scrollTarget in findFirstChangedChild()
        setTimeout(() => {
            scrollTarget.style.transition = '';
            if(!origHasStyleAttribute)
                scrollTarget.removeAttribute('style');
        }, 573);
    }
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

    getWebsocket().then((websocket) => websocket.send('filepath:' + newFullFpath));
    return false;
}

function footnoteClickEvent(event)
{
    let a = event.target;
    while(a && a.tagName != 'A')
        a = a.parentNode;
    if(!a)
        return true;

    // Push state so browser back button jumps to previous position
    history.pushState(history.state, fpath);
    window.scrollTo({top: a._footnoteHref.getBoundingClientRect().top + window.pageYOffset});
    return false;
}

function extractFootnotes(newEl, newFn)
{
    // Check for section with class 'footnotes'
    let fn = newEl.firstElementChild;
    while(fn && !fn.classList.contains('footnotes'))
        fn = fn.nextElementSibling;
    if(!fn)
        return false;

    // Check for ol
    let ol = fn.firstElementChild;
    while(ol && ol.tagName != 'OL')
        ol = ol.nextElementSibling;
    if(!ol)
        return false;

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
        li.removeAttribute('id'); // not unique
        for(const aback of li.getElementsByTagName('a')) {
            if(aback.getAttribute('href') == '#fnref'+num) {
                const aref = document.getElementById('fnref'+num);
                aref.removeAttribute('id'); // not unique
                aref._footnoteHref = aback;
                aref.onclick = footnoteClickEvent;

                li._footnoteAref = aref;
                aback._footnoteHref = aref;
                aback.onclick = footnoteClickEvent;

                break; // Should only be one such link
            }
        }

        // Move footnote to global footnotes
        ol.removeChild(li);
        newFn.appendChild(li);
    }

    // Remove footnotes container
    newEl.removeChild(fn);

    return true;
}

function extractReferences(newEl)
{
    let hasNewTextCites = false;
    const referenceElements = [];

    for(const el of newEl.getElementsByClassName('citation')) {
        const citekeys = el.getAttribute('data-cites').split(' ');
        const textcite = el.textContent;

        // Save all used citekeys for this citation (in order!)
        el._referenceCitekeys = citekeys;

        // Save textcite for later.
        el._referenceTextcite = textcite;

        // Update _citekeyRefcounts.
        for(const citekey of citekeys) {
            if(_citekeyRefcounts[citekey] === undefined)
                _citekeyRefcounts[citekey] = 1;
            else
                _citekeyRefcounts[citekey]++;
        }

        // If we know this textcite's html, directly use it
        // Otherwise, we have to request it from the websocket
        // In any case, push this element into the textcitesCache
        const cache = _textcitesCache[textcite];
        if(cache === undefined) {
            hasNewTextCites = true;
            _textcitesCache[textcite] = {elements: [el]};
        } else {
            cache.elements.push(el);
            if(cache.html !== undefined)
                el.innerHTML = cache.html;
        }

        referenceElements.push(el);
    }

    // Save all reference elements.
    newEl._referenceElements = referenceElements;

    return hasNewTextCites;
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
        _refsElement.style.display = suppressBibliography ? 'none' : 'block';
        references.style.display = suppressBibliography || _refsElement.parentNode !== references  ? 'none' : 'block';
    } else
        references.style.display = 'none';
}

function citeprocResultEvent(message)
{
    console.log(performance.now(), 'citeproc result event');

    // parse the HTML in a temporary container
    const div = document.createElement('div');
    div.innerHTML = message;

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

            // Update all with the same textcite, if HTML has changed
            const html = citeprocCitations[i-1].innerHTML;
            const textciteCache = _textcitesCache[textcite];
            if(!textciteCache) {
                // Can in principle happen due to async-ness of everything
                showStatusWarning('Received citations for old request. Maybe try reloading?');
                return;
            }
            if(textciteCache.html == html)
                continue;
            textciteCache.html = html;
            for(const tmp of textciteCache.elements)
                tmp.innerHTML = html;
        }
    }
    if(i != citeprocCitations.length) {
        // Can in principle happen due to async-ness of everything
        showStatusWarning('Received citations for different request. Maybe try reloading?');
        return;
    }

    // Replace reference list with new reference list, if any
    const refList = div.querySelector('.references');
    if(refList) {
        refList.id = 'pmpmRefs'; // avoid collision with custom <div id="refs">
        replaceRefList(refList);
        showHideRefList();
    }

    console.log(performance.now(), 'citeproc done');
}

const _citekeyRefcounts = {};
const _textcitesCache = {};
let _refsElement;
function updateBodyFromBlocks(contentnew, referenceSectionTitle)
{
    console.log(performance.now(), 'start updateBody')
    // Go through new content blocks. At each step we ensure that <div id="content"> matches the new contents up to block i
    let i;
    let firstChange;
    let firstChangeCompare;
    let mustRenumber = false;
    let renumberNum;
    let hasNewTextCites = false;
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
                if(footnotesChildren[j].childElementCount || footnotesChildren[i].childElementCount) {
                    swapElements(footnotes, footnotesChildren[j], footnotesChildren[i]);
                    mustRenumber = true;
                }

                if (firstChange === undefined) {
                    firstChange = children[i];
                    firstChangeCompare = children[j];
                }
            }
        } else {
            // Hash does not exist, creating new
            const newEl = document.createElement('div');
            newEl.setAttribute(hashAttr, newhash);
            newEl.innerHTML = contentnew[i][1];
            container.insertBefore(newEl, children[i]);

            // Create footnotes placeholder
            const newFn = document.createElement('ol');
            footnotes.insertBefore(newFn, footnotesChildren[i]);

            // Check footnotes.
            if(extractFootnotes(newEl, newFn))
                mustRenumber = true;

            // Check references
            if(extractReferences(newEl))
                hasNewTextCites = true;

            // asynchronously render latex and viz if necessary
            renderBlockContentsAsync(newEl);

            if (firstChange === undefined) {
                firstChange = children[i];
                firstChangeCompare = children[i+1];
            }
        }

        // Renumber footnotes if necessary
        if(mustRenumber) {
            const fnBlock = footnotesChildren[i];
            if(renumberNum === undefined) {
                const tmp = fnBlock.previousElementSibling;
                renumberNum = tmp ? tmp.start + tmp.childElementCount - 1 : 0;
            }
            fnBlock.start = renumberNum+1;
            for(const li of fnBlock.children)
                li._footnoteAref.firstElementChild.textContent = ++renumberNum;
        }
    }

    // Now all non-needed elements from original content should be at the end and we can remove them
    while(children.length > i) {
        const block = container.lastElementChild;

        // Update references
        const referenceElements = block._referenceElements;
        if(referenceElements !== undefined) {
            for(const el of referenceElements) {

                // Remove refcounts in _citekeyRefcounts
                for(const citekey of el._referenceCitekeys) {
                    if(_citekeyRefcounts[citekey] == 1) {
                        delete _citekeyRefcounts[citekey];
                        // Remove this from references, if present
                        const refEl = document.getElementById('ref-'+citekey);
                        if(refEl)
                            refEl.parentNode.removeChild(refEl);
                    } else
                        _citekeyRefcounts[citekey]--;
                }

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
        footnotes.removeChild(footnotes.lastElementChild);
    }

    if (firstChange !== undefined) {
        // Show/hide footnotes
        const showFootnotes = footnotes.lastElementChild.start > 1 || footnotes.lastElementChild.childElementCount;
        footnotes.parentNode.style.display = showFootnotes ? 'block': 'none';

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

    if(firstChange !== undefined) {
        // scroll first changed block into view
        scrollToFirstChange(firstChange, firstChangeCompare);
    }

    // Set references title
    if(referenceSectionTitle !== "") {
        referencesTitle.textContent = referenceSectionTitle;
        referencesTitle.style.display = "";
    } else
        referencesTitle.style.display = "none";

    console.log(performance.now(), 'end updateBody');

    // Render references asynchronously
    if(hasNewTextCites)
        getWebsocket().then(websocket => websocket.send('citeproc'));
}

// websockets
function showStatusWarning(text)
{
    status.style.display = 'block';
    status.style.backgroundColor = 'yellow';
    status.textContent = text;
}

function showStatusInfo(text)
{
    status.style.display = 'block';
    status.style.backgroundColor = 'lightgray';
    status.textContent = text;
}

function hideStatus()
{
    status.style.display = 'none';
}

const websocketUrl = "ws://localhost:9877/";
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
            suppressBibliography = message["suppress-bibliography"];
            updateBodyFromBlocks(message.htmlblocks, message["reference-section-title"]);
        } else {
            if(message.error !== undefined) {
                showStatusWarning(message.error);
                return;
            }
            if(message.status !== undefined) {
                showStatusInfo(message.status);
                return;
            }
            // Async citeproc result
            citeprocResultEvent(message);
            return;
        }

        // change browser url
        if (message.filepath != fpath) {
            const url = "?filepath=" + encodeURIComponent(message.filepath);
            fpath = message.filepath;
            window.document.title = 'pmpm - '+fpath;
            history.pushState({fpath:fpath}, fpath, url);
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
    getWebsocket().then((websocket) => websocket.send('filepath:' + fpath));
};

// Load websocket
initWebsocket();

// Load initial document if any
if(fpath && fpath !== 'LIVE') {
    window.document.title = 'pmpm - '+fpath;
    getWebsocket().then((websocket) => websocket.send('filepath:' + fpath));
} else {
    // When refreshing the page, it may be irritatingly empty --> show this
    getWebsocket().then((_) => showStatusInfo('Just connected to '+websocketUrl+'. Pipe something to pmpm ;-)'));
}

