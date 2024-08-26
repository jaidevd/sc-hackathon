const PAGE_TO_VIEW = 1;
const SCALE = 1.0;

const ENABLE_XFA = true;

async function renderPDF(url) {
  let container = document.getElementById("viewContainer");

  let eventBus = new pdfjsViewer.EventBus();

  let loadingTask = pdfjsLib.getDocument({
    url: url,
    enableXfa: ENABLE_XFA,
  });

  let pdfDocument = await loadingTask.promise;
  let pdfPage = await pdfDocument.getPage(PAGE_TO_VIEW);

  let pdfPageView = new pdfjsViewer.PDFPageView({
    container,
    id: PAGE_TO_VIEW,
    scale: SCALE,
    defaultViewport: pdfPage.getViewport({ scale: SCALE }),
    eventBus,
  });
  pdfPageView.setPdfPage(pdfPage);
  await pdfPageView.draw();
  container.classList.add('bg-secondary')
}
