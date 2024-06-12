document.addEventListener("DOMContentLoaded", function() {
    const container = document.querySelector('.container');
    container.style.opacity = 0;
    container.style.transition = 'opacity 1s';
    setTimeout(() => {
        container.style.opacity = 1;
    }, 100);
});
