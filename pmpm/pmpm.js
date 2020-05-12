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
let fpath = (new URLSearchParams(window.location.search)).get('fpath');


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
            errEl.innerText = latexStr + ' ('+e.message+')';
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
            if(curChild.nodeType != Node.ELEMENT_NODE)
                return curChild.parentNode;
            else if(!curChild.childNodes.length)
                return curChild;
            else
                return findFirstChangedChild(curChild.childNodes, prevChild.childNodes);
        }
    }
    return currentChildNodes[nchildren-1];
}

function extractFootnotes(newEl, newFn, newhash)
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
        li.id = newhash+li.id;
        for(const aback of li.getElementsByTagName('a')) {
            if(aback.getAttribute('href') == '#fnref'+num) {
                aback.setAttribute('href', '#'+newhash+'fnref'+num);
                const aref = document.getElementById('fnref'+num);
                aref.id = newhash+aref.id;
                aref.setAttribute('href', '#'+newhash+'fn'+num);
                li.setAttribute('data-aref', aref.id);
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

function updateBodyFromBlocks(contentnew)
{
    // Go through new content blocks. At each step we ensure that <div id="content"> matches the new contents up to block i
    let i;
    let scrollTarget;
    let scrollTargetCompare;
    let mustRenumber = false;
    let renumberNum;
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

                if (scrollTarget === undefined) {
                    scrollTarget = children[i];
                    scrollTargetCompare = children[j];
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

            // Check footnotes
            if(extractFootnotes(newEl, newFn, newhash))
                mustRenumber = true;

            // asynchronously render latex and viz if necessary
            renderBlockContentsAsync(newEl);

            if (scrollTarget === undefined) {
                scrollTarget = children[i];
                scrollTargetCompare = children[i+1];
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
                document.getElementById(li.getAttribute('data-aref')).firstElementChild.innerText = ++renumberNum;
        }
    }

    // Now all non-needed elements from original content should be at the end and we can remove them
    while(children.length > i) {
        container.removeChild(container.lastElementChild);
        footnotes.removeChild(footnotes.lastElementChild);
    }

    if (scrollTarget !== undefined) {
        // Show/hide footnotes
        footnotes.parentNode.style.display = renumberNum ? 'block': 'none';

        // scroll first changed block into view
        // TODO: Delay until async katex / viz rendering is done?
        if(scrollTargetCompare && scrollTarget.childNodes.length)
            scrollTarget = findFirstChangedChild(scrollTarget.childNodes, scrollTargetCompare.childNodes);
        window.scrollTo({top:
            scrollTarget.getBoundingClientRect().top +
            window.pageYOffset - window.innerHeight / 5})
    }
}

// websockets
function showStatusWarning(text)
{
    status.style.display = 'block';
    status.style.backgroundColor = 'yellow';
    status.innerText = text;
}

function showStatusInfo(text)
{
    status.style.display = 'block';
    status.style.backgroundColor = 'lightgray';
    status.innerText = text;
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

        // update page
        updateBodyFromBlocks(message.htmlblocks);

        // change browser url
        const url = window.location.pathname + "?fpath=" + encodeURIComponent(message.fpath);
        if (message.fpath !== "" && message.fpath != fpath) {
            fpath = message.fpath;
            window.document.title = 'pmpm - '+fpath;
            history.pushState({fpath:fpath}, url, url);
        } else {
            history.replaceState({fpath:fpath}, url, url);
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
            _websocketPromise.then(() => showStatusInfo('Just connected to '+websocketUrl+'. Shown content is possibly outdated.'));
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

window.onpopstate = history.onpushstate = function (event) {

    // Don't do anything on scroll to footnotes
    if(event.state === null)
        return;

    fpath = event.state.fpath;
    window.document.title = 'pmpm - '+fpath;
    getWebsocket().then((websocket) => websocket.send(fpath));
};

// Load websocket
initWebsocket();

// Load initial document if any
if(fpath) {
    window.document.title = 'pmpm - '+fpath;
    getWebsocket().then((websocket) => websocket.send(fpath));
}