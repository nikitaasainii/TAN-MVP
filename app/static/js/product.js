(function () {
  var form = document.getElementById('order-form');
  if (!form) return;

  var money = function (v) {
    return '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var priceEl = document.getElementById('price');
  var base = +priceEl.dataset.base, fee = +priceEl.dataset.fee;
  var fit = document.getElementById('custom_fit');
  var fitBox = document.getElementById('fit-box');
  var fitNote = document.getElementById('fit-note');
  var fitCount = document.getElementById('fit-count');
  var colourName = document.getElementById('colour-name');
  var photo = document.getElementById('photo');
  var uploadText = document.getElementById('upload-text');
  var preview = document.getElementById('upload-preview');
  var addBtn = document.getElementById('add-to-cart');
  var buyBtn = document.getElementById('buy-now');
  var saveBtn = document.getElementById('save-edit');
  var editIndex = form.dataset.editIndex;
  var buttons = [addBtn, buyBtn, saveBtn].filter(Boolean);

  // ---- Sprint 2: fabric info card and suitability hint ----
  var fabricData = JSON.parse(document.getElementById('fabric-data').textContent);
  var fabEmpty = document.getElementById('fabric-empty');
  var fabInfo = document.getElementById('fabric-info');
  var fabWarning = document.getElementById('fabric-warning');
  function showFabric(name) {
    var d = fabricData.details[name];
    fabEmpty.hidden = !!d;
    fabInfo.hidden = !d;
    if (d) {
      document.getElementById('fab-name').textContent = name;
      document.getElementById('fab-desc').textContent = d.description;
      document.getElementById('fab-drape').textContent = d.drape;
      document.getElementById('fab-stretch').textContent = d.stretch;
      document.getElementById('fab-care').textContent = d.care;
    }
    var w = fabricData.warnings[name];
    fabWarning.textContent = w ? 'Heads up: ' + w : '';
    fabWarning.hidden = !w;
  }
  form.querySelectorAll('input[name=fabric]').forEach(function (r) {
    r.addEventListener('change', function () { showFabric(r.value); });
  });
  var pickedFabric = form.querySelector('input[name=fabric]:checked');
  if (pickedFabric) showFabric(pickedFabric.value);

  fit.addEventListener('change', function () {
    fitBox.hidden = !fit.checked;
    priceEl.textContent = money(base + (fit.checked ? fee : 0));
    if (fit.checked) fitNote.focus();
  });
  fitNote.addEventListener('input', function () { fitCount.textContent = fitNote.value.length; });

  form.querySelectorAll('input[name=colour]').forEach(function (r) {
    r.addEventListener('change', function () { colourName.textContent = r.dataset.name; });
  });

  photo.addEventListener('change', function () {
    preview.replaceChildren();
    var f = photo.files[0];
    if (!f) { preview.hidden = true; uploadText.textContent = 'Upload a photo of the look you have in mind'; return; }
    uploadText.textContent = 'Change photo';
    var keep = document.getElementById('remove_photo'); if (keep) keep.checked = false;
    var img = document.createElement('img');
    img.src = URL.createObjectURL(f);
    img.alt = 'Selected reference photo';
    var name = document.createElement('span');
    name.textContent = f.name;
    preview.appendChild(img); preview.appendChild(name);
    preview.hidden = false;
  });

  function clearErrors() {
    form.querySelectorAll('.field-error').forEach(function (p) { p.hidden = true; p.textContent = ''; });
  }
  function showErrors(errors) {
    var first = null;
    Object.keys(errors).forEach(function (key) {
      var p = form.querySelector('[data-error="' + key + '"]');
      if (p) { p.textContent = errors[key]; p.hidden = false; if (!first) first = p; }
    });
    if (first) first.scrollIntoView({ block: 'center' });
  }
  function setBusy(b) { buttons.forEach(function (x) { x.disabled = b; }); }

  async function submit(url) {
    clearErrors();
    var fd = new FormData(form);
    if (editIndex !== undefined) fd.append('index', editIndex);
    var errs = {};
    if (!fd.get('size')) errs.size = 'Please select a size.';
    if (!fd.get('fabric')) errs.fabric = 'Please choose a fabric.';
    if (!fd.get('colour')) errs.colour = 'Please choose a colour.';
    if (Object.keys(errs).length) { showErrors(errs); return false; }
    setBusy(true);
    try {
      var res = await fetch(url || '/cart/add', { method: 'POST', body: fd });
      var data = await res.json();
      if (!data.ok) { showErrors(data.errors || { form: 'Something went wrong. Please try again.' }); return false; }
      window.TANCart.render(data.cart);
      return true;
    } catch (e) {
      showErrors({ form: 'Could not reach the server. Please try again.' });
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (addBtn) addBtn.addEventListener('click', async function () { if (await submit()) window.TANCart.open(); });
  if (buyBtn) buyBtn.addEventListener('click', async function () { if (await submit()) window.location.href = '/review'; });
  if (saveBtn) saveBtn.addEventListener('click', async function () { if (await submit('/cart/update')) window.location.href = '/review'; });
})();
