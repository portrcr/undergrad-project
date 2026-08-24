// Accessible header navigation: mobile menu toggle + click-driven dropdowns.
(function () {
    'use strict';

    var header = document.querySelector('.site-header');
    if (!header) {
        return;
    }

    var navToggle = header.querySelector('.nav-toggle');
    var nav = header.querySelector('#site-nav');
    var dropdowns = Array.prototype.slice.call(header.querySelectorAll('.nav-dropdown'));

    function closeDropdowns(except) {
        dropdowns.forEach(function (dropdown) {
            if (dropdown === except) {
                return;
            }
            dropdown.classList.remove('open');
            dropdown.querySelector('.nav-dropdown-toggle').setAttribute('aria-expanded', 'false');
        });
    }

    function closeMenu() {
        if (!navToggle || !nav) {
            return;
        }
        nav.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
    }

    dropdowns.forEach(function (dropdown) {
        var toggle = dropdown.querySelector('.nav-dropdown-toggle');

        toggle.addEventListener('click', function () {
            var isOpen = dropdown.classList.contains('open');
            closeDropdowns(dropdown);
            dropdown.classList.toggle('open', !isOpen);
            toggle.setAttribute('aria-expanded', String(!isOpen));
        });
    });

    if (navToggle && nav) {
        navToggle.addEventListener('click', function () {
            var isOpen = nav.classList.contains('open');
            nav.classList.toggle('open', !isOpen);
            navToggle.setAttribute('aria-expanded', String(!isOpen));
            if (isOpen) {
                closeDropdowns();
            }
        });
    }

    // Click outside closes everything that is open.
    document.addEventListener('click', function (event) {
        if (!header.contains(event.target)) {
            closeDropdowns();
            closeMenu();
        }
    });

    // Escape closes the innermost open thing and restores focus.
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') {
            return;
        }

        var openDropdown = header.querySelector('.nav-dropdown.open');
        if (openDropdown) {
            closeDropdowns();
            openDropdown.querySelector('.nav-dropdown-toggle').focus();
            return;
        }

        if (nav && nav.classList.contains('open')) {
            closeMenu();
            navToggle.focus();
        }
    });
})();
