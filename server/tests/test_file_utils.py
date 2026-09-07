from utils.file_utils import is_supported_audio_filename


def test_supported_audio_extensions_include_wav_mp3_and_m4a():
    assert is_supported_audio_filename("sample.wav")
    assert is_supported_audio_filename("sample.WAV")
    assert is_supported_audio_filename("sample.mp3")
    assert is_supported_audio_filename("sample.MP3")
    assert is_supported_audio_filename("sample.m4a")
    assert is_supported_audio_filename("sample.M4A")
    assert is_supported_audio_filename("sample.aac")


def test_unsupported_audio_extension_is_rejected():
    assert not is_supported_audio_filename("sample.flac")
    assert not is_supported_audio_filename("sample.txt")
    assert not is_supported_audio_filename(None)

