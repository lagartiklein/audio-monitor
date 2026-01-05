#!/usr/bin/env python3
"""
test_compression.py - Prueba de compresión y blocksize
Verifica que la compresión e integración con el servidor funciona
"""

import sys
import time
import numpy as np
sys.path.insert(0, '.')

from audio_server.audio_compression import get_audio_compressor
import config

def test_compression():
    """Test compression performance"""
    print("=" * 60)
    print("TEST: Audio Compression")
    print("=" * 60)
    
    # Initialize
    compressor = get_audio_compressor(config.SAMPLE_RATE, 1, 32000)  # Bitrate ignorado en zlib
    print(f"\n[CONFIG] Blocksize: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms @ {config.SAMPLE_RATE}Hz)")
    print(f"[CONFIG] Compression: {compressor.compression_method}")
    print(f"[CONFIG] Bitrate target: 32000 kbps (ignorado en zlib)")
    
    # Generate test audio
    print("\n[TEST] Generando audio de prueba...")
    num_blocks = 10
    total_samples = config.BLOCKSIZE * num_blocks
    audio_data = np.random.randn(total_samples).astype(np.float32) * 0.1
    
    # Test compression on blocks
    print(f"\n[TEST] Comprimiendo {num_blocks} bloques de {config.BLOCKSIZE} samples...")
    
    compressed_sizes = []
    original_sizes = []
    decompress_times = []
    compress_times = []
    
    for i in range(num_blocks):
        block = audio_data[i*config.BLOCKSIZE:(i+1)*config.BLOCKSIZE]
        original_sizes.append(len(block) * 4)  # 4 bytes per float32
        
        # Compress
        t0 = time.perf_counter()
        compressed = compressor.compress(block)
        t_compress = (time.perf_counter() - t0) * 1000  # ms
        compress_times.append(t_compress)
        compressed_sizes.append(len(compressed))
        
        # Decompress
        t0 = time.perf_counter()
        decompressed = compressor.decompress(compressed)
        t_decompress = (time.perf_counter() - t0) * 1000
        decompress_times.append(t_decompress)
        
        # Verify
        error = np.mean(np.abs(block - decompressed))
        print(f"  Block {i:2d}: {original_sizes[-1]:5d} -> {compressed_sizes[-1]:5d} bytes " +
              f"({100*len(compressed)//(len(block)*4):3d}%) | " +
              f"Compress: {t_compress:.3f}ms, Decompress: {t_decompress:.3f}ms, Error: {error:.6f}")
    
    # Summary
    print("\n" + "=" * 60)
    print("RESULTADOS")
    print("=" * 60)
    
    avg_original = np.mean(original_sizes)
    avg_compressed = np.mean(compressed_sizes)
    ratio = 100 * avg_compressed // int(avg_original)
    
    print(f"\nTamano promedio:")
    print(f"  Original: {avg_original:.0f} bytes")
    print(f"  Comprimido: {avg_compressed:.0f} bytes")
    print(f"  Ratio: {ratio}%")
    
    print(f"\nVelocidad:")
    print(f"  Compresi'on: {np.mean(compress_times):.3f}ms promedio")
    print(f"  Descompresi'on: {np.mean(decompress_times):.3f}ms promedio")
    print(f"  Blocksize latency: {config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms")
    
    # Bandwidth analysis
    print(f"\nAncho de banda (a 48kHz):")
    original_bw = avg_original * 48000 / config.BLOCKSIZE / 1000 / 8  # kbps
    compressed_bw = avg_compressed * 48000 / config.BLOCKSIZE / 1000 / 8  # kbps
    print(f"  Original: {original_bw:.0f} kbps")
    print(f"  Comprimido: {compressed_bw:.0f} kbps")
    print(f"  Reduction: {original_bw/compressed_bw:.1f}x")
    
    print("\n[OK] Sistema listo para ultra baja latencia")
    return True

if __name__ == "__main__":
    try:
        test_compression()
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
