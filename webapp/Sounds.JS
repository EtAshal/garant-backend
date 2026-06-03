// ══════════════════════════════════════════════════════
// ГАРАНТЪ — Звуковая система на Tone.js
// ══════════════════════════════════════════════════════

const GARANT_SOUNDS = (() => {
    let ready = false;
    let enabled = true;

    // Инициализируем Tone.js при первом касании
    async function init() {
        if (ready) return;
        await Tone.start();
        ready = true;
    }

    // Основной реверб для атмосферы
    const reverb = new Tone.Reverb({ decay: 2.5, wet: 0.35 }).toDestination();
    const delay  = new Tone.FeedbackDelay("8n", 0.2).connect(reverb);

    // ── 1. КОЛОКОЛ — создание сделки / успех ──────────────────
    function bell() {
        if (!enabled) return;
        const bell = new Tone.MetalSynth({
            frequency: 440,
            envelope: { attack: 0.001, decay: 1.8, release: 0.5 },
            harmonicity: 5.1,
            modulationIndex: 32,
            resonance: 4000,
            octaves: 1.5,
            volume: -8
        }).connect(reverb);

        const now = Tone.now();
        bell.triggerAttackRelease("C5", "2n", now);
        bell.triggerAttackRelease("G5", "2n", now + 0.15);
        bell.triggerAttackRelease("E5", "2n", now + 0.3);

        setTimeout(() => bell.dispose(), 4000);
    }

    // ── 2. МОНЕТЫ — принятие сделки / оплата ──────────────────
    function coins() {
        if (!enabled) return;
        const synth = new Tone.MetalSynth({
            frequency: 800,
            envelope: { attack: 0.001, decay: 0.15, release: 0.05 },
            harmonicity: 3.1,
            modulationIndex: 16,
            resonance: 3000,
            octaves: 0.5,
            volume: -10
        }).connect(reverb);

        const now = Tone.now();
        // Несколько монет падают друг за другом
        [0, 0.08, 0.18, 0.3, 0.38].forEach((t, i) => {
            const freq = 600 + Math.random() * 400;
            synth.triggerAttackRelease(freq, "32n", now + t);
        });

        setTimeout(() => synth.dispose(), 2000);
    }

    // ── 3. ФАНФАРЫ — конфетти / большой успех ─────────────────
    function fanfare() {
        if (!enabled) return;
        const synth = new Tone.Synth({
            oscillator: { type: "triangle" },
            envelope: { attack: 0.01, decay: 0.1, sustain: 0.6, release: 0.3 },
            volume: -12
        }).connect(reverb);

        const now = Tone.now();
        const notes = ["C4", "E4", "G4", "C5", "E5"];
        notes.forEach((note, i) => {
            synth.triggerAttackRelease(note, "8n", now + i * 0.12);
        });

        // Добавляем барабан
        const drum = new Tone.MembraneSynth({
            pitchDecay: 0.05,
            octaves: 4,
            envelope: { attack: 0.001, decay: 0.3, sustain: 0, release: 0.1 },
            volume: -15
        }).connect(reverb);
        drum.triggerAttackRelease("C2", "8n", now + 0.48);
        drum.triggerAttackRelease("C2", "8n", now + 0.6);

        setTimeout(() => { synth.dispose(); drum.dispose(); }, 3000);
    }

    // ── 4. СВИТОК — открытие/закрытие панели ──────────────────
    function scroll() {
        if (!enabled) return;
        // Шелест пергамента — шум с фильтром
        const noise = new Tone.Noise("brown").connect(
            new Tone.AutoFilter({
                frequency: 4,
                baseFrequency: 300,
                octaves: 2
            }).connect(
                new Tone.Envelope({
                    attack: 0.05,
                    decay: 0.3,
                    sustain: 0,
                    release: 0.1
                }).connect(reverb)
            )
        );

        const env = new Tone.AmplitudeEnvelope({
            attack: 0.02,
            decay: 0.4,
            sustain: 0,
            release: 0.1,
            volume: -20
        }).toDestination();

        const noiseSimple = new Tone.Noise("pink");
        const filter = new Tone.Filter(1200, "bandpass");
        noiseSimple.connect(filter);
        filter.connect(env);
        env.connect(reverb);

        noiseSimple.start();
        env.triggerAttackRelease(0.35);

        // Низкий тон как разворачивание
        const synth = new Tone.Synth({
            oscillator: { type: "sine" },
            envelope: { attack: 0.05, decay: 0.4, sustain: 0, release: 0.2 },
            volume: -18
        }).connect(reverb);
        synth.triggerAttackRelease("G2", "4n", Tone.now() + 0.05);

        setTimeout(() => {
            noiseSimple.stop();
            noiseSimple.dispose();
            filter.dispose();
            env.dispose();
            synth.dispose();
        }, 1500);
    }

    // ── 5. ПОДТВЕРЖДЕНИЕ — всё ок ─────────────────────────────
    function confirm() {
        if (!enabled) return;
        const synth = new Tone.PolySynth(Tone.Synth, {
            oscillator: { type: "sine" },
            envelope: { attack: 0.02, decay: 0.3, sustain: 0.4, release: 0.8 },
            volume: -14
        }).connect(reverb);

        const now = Tone.now();
        // Мажорный аккорд
        synth.triggerAttackRelease(["C4", "E4", "G4"], "4n", now);
        synth.triggerAttackRelease(["E4", "G4", "C5"], "2n", now + 0.2);

        setTimeout(() => synth.dispose(), 3000);
    }

    // ── 6. ОТМЕНА — отказ от сделки ───────────────────────────
    function cancel() {
        if (!enabled) return;
        const synth = new Tone.Synth({
            oscillator: { type: "sawtooth" },
            envelope: { attack: 0.01, decay: 0.4, sustain: 0.1, release: 0.3 },
            volume: -16
        }).connect(reverb);

        const now = Tone.now();
        synth.triggerAttackRelease("A3", "8n", now);
        synth.triggerAttackRelease("F3", "8n", now + 0.15);
        synth.triggerAttackRelease("D3", "4n", now + 0.3);

        setTimeout(() => synth.dispose(), 2000);
    }

    // ── 7. СПОР — тревога ─────────────────────────────────────
    function dispute() {
        if (!enabled) return;
        // Рог тревоги
        const synth = new Tone.Synth({
            oscillator: { type: "sawtooth" },
            envelope: { attack: 0.05, decay: 0.1, sustain: 0.8, release: 0.3 },
            volume: -14
        }).connect(reverb);

        const now = Tone.now();
        synth.triggerAttackRelease("G3", "8n", now);
        synth.triggerAttackRelease("G3", "8n", now + 0.2);
        synth.triggerAttackRelease("D3", "4n", now + 0.4);

        // Барабан тревоги
        const drum = new Tone.MembraneSynth({
            pitchDecay: 0.08,
            octaves: 3,
            volume: -16
        }).connect(reverb);
        [0, 0.15, 0.3, 0.45, 0.6].forEach(t => {
            drum.triggerAttackRelease("C2", "16n", now + t);
        });

        setTimeout(() => { synth.dispose(); drum.dispose(); }, 3000);
    }

    // ── 8. ЩЕЛЧОК — переключение вкладок ──────────────────────
    function click() {
        if (!enabled) return;
        const synth = new Tone.Synth({
            oscillator: { type: "sine" },
            envelope: { attack: 0.001, decay: 0.08, sustain: 0, release: 0.02 },
            volume: -20
        }).connect(reverb);
        synth.triggerAttackRelease("C5", "64n");
        setTimeout(() => synth.dispose(), 500);
    }

    // ── 9. ПЕЧАТЬ СУРГУЧА — скрепление документа ──────────────
    function seal() {
        if (!enabled) return;
        // Глухой удар
        const drum = new Tone.MembraneSynth({
            pitchDecay: 0.12,
            octaves: 5,
            envelope: { attack: 0.001, decay: 0.4, sustain: 0, release: 0.1 },
            volume: -10
        }).connect(reverb);
        drum.triggerAttackRelease("A1", "8n");

        // Хруст воска
        const noise = new Tone.Noise("white");
        const filter = new Tone.Filter(2000, "highpass");
        const env = new Tone.AmplitudeEnvelope({
            attack: 0.001, decay: 0.12, sustain: 0, release: 0.05,
        }).toDestination();
        noise.connect(filter);
        filter.connect(env);
        noise.start();
        env.triggerAttackRelease(0.12, Tone.now() + 0.05);

        setTimeout(() => {
            noise.stop(); noise.dispose();
            filter.dispose(); env.dispose(); drum.dispose();
        }, 1500);
    }

    return {
        init,
        bell,
        coins,
        fanfare,
        scroll,
        confirm,
        cancel,
        dispute,
        click,
        seal,
        enable:  () => { enabled = true; },
        disable: () => { enabled = false; },
        toggle:  () => { enabled = !enabled; return enabled; }
    };
})();

// Автоинициализация при первом касании
document.addEventListener('touchstart',  () => GARANT_SOUNDS.init(), { once: true });
document.addEventListener('click',       () => GARANT_SOUNDS.init(), { once: true });