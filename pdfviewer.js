const PAGE_TO_VIEW = 1;
const SCALE = 1.0;

const ENABLE_XFA = true;


async function loadDocument(url) {
  let loadingTask = pdfjsLib.getDocument({
    url: url,
    enableXfa: ENABLE_XFA,
  });
  let pdfDocument = await loadingTask.promise;
  return pdfDocument
}

async function renderPage(doc, page, view) {
  let eventBus = new pdfjsViewer.EventBus();
  let pdfPage = await doc.getPage(page);
  let container = document.getElementById("viewContainer");
  if (!(view)) {
    view = new pdfjsViewer.PDFPageView({
      container,
      id: page,
      scale: SCALE,
      defaultViewport: pdfPage.getViewport({ scale: SCALE }),
      eventBus,
    });
  }
  view.setPdfPage(pdfPage);
  await view.draw();
  container.classList.add('bg-secondary')
  return view
}

function drawAnnotationBox(tr) {
  let canvas = document.querySelector('canvas')
  let [width, height] = [canvas.offsetWidth, canvas.offsetHeight]
  let svg = document.querySelector('svg')
  svg = svg ? SVG(svg) : SVG().addTo(".canvasWrapper").size("100%", "100%")
  svg.node.style.top = `${canvas.offsetTop}`;
  svg.node.style.left = `${canvas.offsetLeft}`;
  let [w, h] = [Number(tr.width) * width, Number(tr.height) * height]
  let [xmin, ymin] = [Number(tr.x) * width, Number(tr.y) * height]
  let rect = svg.rect(w, h).attr({ fill: '#76ff07', opacity: 0.3 }).move(xmin, ymin)
  return rect.node
}
