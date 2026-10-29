(function () {
  document.querySelectorAll('.review-remove').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var fd = new FormData();
      fd.append('index', btn.dataset.index);
      btn.disabled = true;
      fetch('/cart/remove', { method: 'POST', body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) { window.location.href = d.cart && d.cart.items.length ? '/review' : '/products'; })
        .catch(function () { btn.disabled = false; });
    });
  });
})();
