/* Mascote compartilhado das ondas internas. Nenhuma dependência ou rede. */
(() => {
    'use strict';
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const mouse = matchMedia('(any-pointer: fine)');
    const states = new Map();
    let pointer = null, frame = 0;
    // A curva superior é percorrida da direita para a esquerda.
    function alturaOnda(path, target) {
        const length = path.getTotalLength();
        let prev = path.getPointAtLength(0);
        for (let i = 2; i <= length; i += 2) {
            const p = path.getPointAtLength(i);
            if (prev.x >= target && p.x <= target && prev.x !== p.x) {
                const fraction = (target - prev.x) / (p.x - prev.x);
                return prev.y + (p.y - prev.y) * fraction;
            }
            prev = p;
        }
        return null;
    }
    function align(state) {
        const {wrap, path} = state;
        const percent = parseFloat(getComputedStyle(wrap).getPropertyValue('--lsd-robo-x'));
        if (!Number.isFinite(percent)) return;
        const target = percent * 12;
        const y = alturaOnda(path, target);
        if (y === null) return;
        wrap.style.setProperty('--lsd-robo-y', `${y / 1.2}%`);
        // Na ficha, cada luva acompanha a altura local da curva. Só as pontas
        // dos dedos ultrapassam a borda: braços e parte inferior ficam ocultos.
        const hands = wrap.querySelector('.robo-escondido-mao');
        const box = wrap.getBoundingClientRect();
        const handBox = hands?.getBoundingClientRect();
        if (!handBox?.width || !box.width || !box.height) return;
        const scale = handBox.width / 128;
        for (const grip of hands.querySelectorAll('[data-lsd-grip]')) {
            const cx = Number(grip.dataset.lsdGrip);
            const gx = target + (cx - 64) * scale * 1200 / box.width;
            const gy = alturaOnda(path, gx);
            if (gy === null) continue;
            const edge = 76 + (gy - y) * box.height / (120 * scale);
            grip.setAttribute('transform', `translate(0 ${edge - 84}) translate(${cx} 84) scale(.78) translate(${-cx} -84)`);
        }
    }
    function draw() {
        frame = 0;
        for (const {wrap, robot, eyes} of states.values()) {
            if (!wrap.getClientRects().length) continue;
            let x = 0, y = -4;
            const rect = robot.getBoundingClientRect();
            if (pointer && !reduced.matches && mouse.matches && rect.bottom >= 0 && rect.top <= innerHeight) {
                const matrix = robot.getScreenCTM();
                if (matrix) {
                    const p = robot.createSVGPoint(); p.x = pointer.x; p.y = pointer.y;
                    const dest = p.matrixTransform(matrix.inverse());
                    const dx = dest.x - 64, dy = dest.y - 64, n = Math.hypot(dx, dy);
                    if (n > 0) { x = 4 * dx / Math.max(n,45); y = 5 * dy / Math.max(n,45); }
                }
            }
            for (const eye of eyes) eye.setAttribute('transform', `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
        }
    }
    function schedule() { if (!frame) frame = requestAnimationFrame(draw); }
    function reset() { pointer = null; schedule(); }
    function refresh() {
        for (const key of states.keys()) if (!key.isConnected) states.delete(key);
        for (const wrap of document.querySelectorAll('.lsd-onda-com-robo')) {
            if (!states.has(wrap)) {
                const robot = wrap.querySelector('.robo-escondido-cabeca');
                const path = wrap.querySelector('.lsd-onda-forma path');
                if (!robot || !path) continue;
                states.set(wrap,{wrap,robot,path,eyes:[...robot.querySelectorAll('[data-robo-olho]')]});
            }
            align(states.get(wrap));
        }
        schedule();
    }
    window.addEventListener('pointermove',e => { if(e.pointerType==='mouse' && !reduced.matches && mouse.matches) {pointer={x:e.clientX,y:e.clientY};schedule();} },{passive:true});
    window.addEventListener('scroll',schedule,{passive:true});
    window.addEventListener('resize',refresh,{passive:true});
    document.documentElement.addEventListener('pointerleave',reset);
    window.addEventListener('blur',reset);
    reduced.addEventListener('change',reset);
    mouse.addEventListener('change',reset);
    document.addEventListener('lsd:projeto-rendered',refresh);
    if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',refresh,{once:true}); else refresh();
})();
