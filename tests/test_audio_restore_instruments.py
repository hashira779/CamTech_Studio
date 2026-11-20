import os
import pytest
from backend import audio_restore

def test_music_chain_preserves_instrument_body():
    p = audio_restore.STRENGTHS["uvr_stems"]
    chain = audio_restore._music_chain(p)
    chain_str = ",".join(chain)
    
    # 1. Must NOT cut off at 55Hz (which kills bass guitars and kick fundamentals)
    assert "highpass=f=55" not in chain_str
    assert "highpass=f=32" in chain_str
    
    # 2. Must NOT apply destructive extrastereo phase-widening which cancels center instruments
    assert "extrastereo" not in chain_str
    
    # 3. Must NOT scoop out 3.5kHz bite from instruments
    assert "equalizer=f=3500:t=q:w=1.0:g=-2.0" not in chain_str
    
    # 4. Must provide warm low-end body around 100Hz
    assert "equalizer=f=100" in chain_str
    
    # 5. Must give backing band presence
    assert "volume=0.8dB" in chain_str

def test_voice_chain_mix_balance():
    p = audio_restore.STRENGTHS["uvr_stems"]
    chain = audio_restore._voice_chain(p)
    chain_str = ",".join(chain)
    
    # Vocal should not brutally drown out the band (+3.5 dB was too loud)
    assert "volume=3.5dB" not in chain_str
    assert f"volume={audio_restore.VOICE_BOOST_DB:.1f}dB" in chain_str

def test_master_eq_chain():
    eq_filters = audio_restore._master_eq_chain(eq_sub=4.0, eq_mid=2.0, eq_high=3.0)
    assert len(eq_filters) == 3
    assert "equalizer=f=60:t=q:w=1.0:g=4.0" in eq_filters[0]
    assert "equalizer=f=2500:t=q:w=1.0:g=2.0" in eq_filters[1]
    assert "equalizer=f=10000:t=q:w=1.0:g=3.0" in eq_filters[2]

def test_master_eq_chain_zero():
    eq_filters = audio_restore._master_eq_chain(0.0, 0.0, 0.0)
    assert len(eq_filters) == 0
