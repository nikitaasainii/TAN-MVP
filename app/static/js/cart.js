(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var money = function (v) {
    return '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var el = function (tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  var backdrop = $('#backdrop');
  var cartDrawer = $('#cart-drawer');
  var navDrawer = $('#nav-drawer');
  var lastFocus = null;

  function show(drawer) {
    lastFocus = document.activeElement;
    backdrop.hidden = false;
    drawer.hidden = false;
    var close = drawer.querySelector('[data-close]');
    if (close) close.focus();
  }
  function closeAll() {
    backdrop.hidden = true;
    cartDrawer.hidden = true;
    navDrawer.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function render(cart) {
    var list = $('#cart-items');
    list.replaceChildren();
    var badge = $('#cart-count');
    if (badge) { badge.textContent = cart.count; badge.hidden = !cart.count; }
    if (!cart.items.length) list.appendChild(el('p', 'cart-empty', 'Your cart is empty.'));
    cart.items.forEach(function (it) {
      var row = el('div', 'cart-item');
      var img = el('img'); img.src = '/static/img/products/' + it.image; img.alt = it.name;
      row.appendChild(img);
      var body = el('div', 'cart-body');
      body.appendChild(el('div', 'cart-name', it.name));
      body.appendChild(el('div', 'cart-meta', 'Size: ' + it.size));
      body.appendChild(el('div', 'cart-meta', 'Fabric: ' + it.fabric));
      body.appendChild(el('div', 'cart-meta', 'Colour: ' + it.colour));
      if (it.custom_fit) body.appendChild(el('div', 'cart-meta', 'Custom Fit Request: ' + (it.custom_fit_note || '')));
      if (it.notes) body.appendChild(el('div', 'cart-meta', 'Notes: ' + it.notes));
      if (it.photo) body.appendChild(el('div', 'cart-meta', 'Reference photo attached'));
      var foot = el('div', 'cart-foot');
      foot.appendChild(el('span', 'cart-qty', 'Qty ' + it.quantity));
      foot.appendChild(el('span', 'cart-price', money(it.line_total)));
      body.appendChild(foot);
      var edit = el('a', 'cart-edit', 'Edit');
      edit.href = '/products/' + it.slug + '?edit=' + it.index;
      body.appendChild(edit);
      row.appendChild(body);
      var rm = el('button', 'cart-remove', '×');
      rm.type = 'button';
      rm.setAttribute('aria-label', 'Remove ' + it.name + ' from cart');
      rm.addEventListener('click', function () { removeItem(it.index); });
      row.appendChild(rm);
      list.appendChild(row);
    });
    $('#cart-subtotal').textContent = money(cart.subtotal);
    $('#checkout-btn').disabled = !cart.items.length;
  }

  function removeItem(index) {
    var fd = new FormData();
    fd.append('index', index);
    fetch('/cart/remove', { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) render(d.cart); });
  }

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAll(); });
  backdrop.addEventListener('click', closeAll);
  document.querySelectorAll('[data-close]').forEach(function (b) { b.addEventListener('click', closeAll); });
  var menuBtn = $('#menu-btn'); if (menuBtn) menuBtn.addEventListener('click', function () { show(navDrawer); });
  var cartBtn = $('#cart-btn'); if (cartBtn) cartBtn.addEventListener('click', function () { show(cartDrawer); });
  $('#checkout-btn').addEventListener('click', function () { window.location.href = '/review'; });

  window.TANCart = { render: render, open: function () { show(cartDrawer); }, close: closeAll };
  render(JSON.parse($('#cart-data').textContent));
})();
