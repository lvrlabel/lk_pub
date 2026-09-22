/**
 * Сторис сообщества: открытие модалки просмотра, реакции и комментарии.
 */
(function () {
    'use strict';

    var modal = document.getElementById('cmStoryModal');
    var body = document.getElementById('cmStoryModalBody');
    if (!modal || !body) return;

    var openedStoryId = null;

    function openStory(card) {
        var details = card.querySelector('.cm-story-details');
        if (!details) return;
        openedStoryId = card.getAttribute('data-story-id');
        body.innerHTML = '';
        var clone = details.cloneNode(true);
        clone.removeAttribute('hidden');
        body.appendChild(clone);
        modal.hidden = false;
        document.body.classList.add('cm-modal-open');
        var media = body.querySelector('.cm-story-details__media img, .cm-story-details__media video');
        if (media && media.tagName === 'IMG' && media.complete === false) {
            media.addEventListener('load', function () {});
        }
    }

    function closeStory() {
        if (!modal || modal.hidden) return;
        modal.hidden = true;
        document.body.classList.remove('cm-modal-open');
        body.innerHTML = '';
        openedStoryId = null;
    }

    function findClosest(target, selector) {
        if (!target || target.nodeType !== 1) return null;
        return target.closest ? target.closest(selector) : null;
    }

    function handleInteraction(e) {
        var opener = findClosest(e.target, '.js-open-story');
        if (opener) {
            e.preventDefault();
            openStory(findClosest(opener, '.cm-story-card'));
            return;
        }
        var closer = findClosest(e.target, '[data-close-story]');
        if (closer) closeStory();
    }

    document.addEventListener('click', handleInteraction);
    document.addEventListener('pointerup', function (e) {
        if (e.pointerType === 'touch') handleInteraction(e);
    }, { passive: false });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeStory();
    });

    // Блокировка прокрутки фона
    var origOverflow = document.body.style.overflow;

    function lockScroll() {
        origOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
    }

    function unlockScroll() {
        document.body.style.overflow = origOverflow;
    }

    var observer = new MutationObserver(function () {
        if (!modal.hidden) lockScroll(); else unlockScroll();
    });
    observer.observe(modal, { attributes: true, attributeFilter: ['hidden'] });
})();