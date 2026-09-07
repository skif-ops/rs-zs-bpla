import numpy as np

from audio.separation import DroneSeparator


def _drone_comb(sample_rate: int, duration: float, f0: float, amplitude: float) -> np.ndarray:
    """Synthesize a steady harmonic comb like a rotor/engine tone."""

    time = np.arange(int(sample_rate * duration)) / sample_rate
    signal = np.zeros_like(time)
    for harmonic in range(1, 11):
        signal += (1.0 / harmonic) * np.sin(2 * np.pi * f0 * harmonic * time)
    return amplitude * signal


def _loud_high_band_noise(sample_rate: int, duration: float, amplitude: float) -> np.ndarray:
    """Broadband high-frequency noise standing in for loud foreground birds."""

    rng = np.random.default_rng(7)
    noise = rng.standard_normal(int(sample_rate * duration))
    # Push most energy above 3 kHz so it survives only outside the drone band.
    chirps = np.zeros_like(noise)
    time = np.arange(noise.size) / sample_rate
    for freq in (3500.0, 5200.0, 7800.0):
        chirps += np.sin(2 * np.pi * freq * time)
    return amplitude * (0.5 * noise + chirps)


def test_separator_isolates_quiet_drone_under_loud_noise():
    sample_rate = 24_000
    duration = 4.0
    drone = _drone_comb(sample_rate, duration, f0=80.0, amplitude=0.05)
    noise = _loud_high_band_noise(sample_rate, duration, amplitude=0.5)
    mix = drone + noise
    mix = mix / np.max(np.abs(mix))

    result = DroneSeparator().separate(mix.astype(np.float64), sample_rate)
    findings = result.findings

    assert findings.drone_present is True
    assert abs(findings.fundamental_hz - 80.0) / 80.0 < 0.15
    assert findings.persistence >= 0.6
    assert findings.harmonic_count >= 4

    # The comb must end up in the isolated signal, not the residual.
    def comb_energy(signal: np.ndarray) -> float:
        spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
        freqs = np.fft.rfftfreq(len(signal), d=1.0 / result.sample_rate)
        power = 0.0
        for harmonic in range(1, 9):
            near = np.abs(freqs - 80.0 * harmonic) <= 3.0
            if np.any(near):
                power += float(np.max(spectrum[near] ** 2))
        return power

    assert comb_energy(result.isolated) > 10.0 * comb_energy(result.residual)


def test_separator_rejects_broadband_noise_without_a_comb():
    sample_rate = 24_000
    duration = 4.0
    noise = _loud_high_band_noise(sample_rate, duration, amplitude=0.5)
    noise = noise / np.max(np.abs(noise))

    findings = DroneSeparator().separate(noise.astype(np.float64), sample_rate).findings

    assert findings.drone_present is False


def test_separator_recovers_moving_comb_under_mains_harmonics():
    sample_rate = 24_000
    duration = 4.0
    time = np.arange(int(sample_rate * duration)) / sample_rate
    drone = _drone_comb(sample_rate, duration, f0=86.0, amplitude=0.08)
    mains = sum(
        amplitude * np.sin(2 * np.pi * frequency * time)
        for frequency, amplitude in ((50.0, 0.40), (100.0, 0.50), (150.0, 0.25), (200.0, 0.35))
    )
    mix = drone + mains
    mix = mix / np.max(np.abs(mix))

    findings = DroneSeparator().separate(mix.astype(np.float64), sample_rate).findings

    assert findings.drone_present is True
    # A subharmonic F0 is acceptable here, but the selected dominant line must
    # be the moving propulsion comb rather than the stronger 100 Hz grid line.
    assert abs(findings.dominant_harmonic_hz - 86.0) / 86.0 < 0.15
    assert abs(findings.dominant_harmonic_hz - 100.0) > 1.0


def test_separator_handles_short_signal():
    sample_rate = 24_000
    tiny = np.zeros(128, dtype=np.float64)

    findings = DroneSeparator().separate(tiny, sample_rate).findings

    assert findings.drone_present is False


def test_separator_does_not_crash_on_short_signal_with_low_rate():
    # A custom low target rate lets a signal shorter than the STFT window pass
    # the size guard; the layout must adapt instead of raising in scipy.stft.
    sample_rate = 8_000
    drone = _drone_comb(sample_rate, duration=0.6, f0=70.0, amplitude=0.2)

    result = DroneSeparator(target_rate=2_000).separate(drone.astype(np.float64), sample_rate)

    assert result.sample_rate == 2_000
    assert result.findings is not None


def test_construction_features_for_clean_electric_comb():
    sample_rate = 24_000
    drone = _drone_comb(sample_rate, duration=4.0, f0=90.0, amplitude=0.3)

    construction = DroneSeparator().separate(drone.astype(np.float64), sample_rate).findings.construction

    assert construction is not None
    assert abs(construction.blade_pass_hz - 90.0) / 90.0 < 0.1
    assert construction.propulsion == "electric"
    assert construction.half_order_ratio < 0.15


def test_propulsion_classifier_logic():
    sep = DroneSeparator()
    assert sep._propulsion(half_ratio=0.04, steadiness_cv=0.01, tonality=0.05)[0] == "electric"
    # Strong half-engine-orders are the 4-stroke combustion signature.
    assert sep._propulsion(half_ratio=0.40, steadiness_cv=0.06, tonality=0.3)[0] == "combustion"


def test_blade_count_from_shaft_subharmonic():
    # Comb at the blade-pass rate (80 Hz) plus a once-per-rev shaft line at 40 Hz
    # implies a 2-blade rotor: blade-pass = 2 x shaft.
    freqs = np.arange(0.0, 320.0, 0.5)
    power = np.full_like(freqs, 1e-6)
    for f in (40.0, 80.0, 160.0, 240.0):
        power[np.argmin(np.abs(freqs - f))] = 1.0

    assert DroneSeparator._estimate_blade_count(freqs, power, fundamental=80.0) == 2


def test_rotor_count_resolves_two_detuned_rotors():
    sample_rate = 24_000
    duration = 4.0
    a = _drone_comb(sample_rate, duration, f0=80.0, amplitude=0.25)
    b = _drone_comb(sample_rate, duration, f0=83.0, amplitude=0.25)
    mix = a + b

    construction = DroneSeparator().separate(mix.astype(np.float64), sample_rate).findings.construction

    assert construction is not None
    assert construction.rotor_count_estimate >= 2
