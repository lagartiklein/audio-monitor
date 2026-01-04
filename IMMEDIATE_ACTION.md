# ⚡ IMMEDIATE ACTION REQUIRED - Audio Crash Fix

## What Happened

Your app crashed with **SIGSEGV (Fatal signal 11)** after ~2 minutes of stable audio playback.

**Root Cause:** Race condition in C++ buffer code when audio buffer saturates.

---

## What You Need To Do

### STEP 1: Recompile Android App (Required)

```
1. Open Android Studio
2. File → Open → Select "kotlin android" folder
3. Build → Clean Project (wait for completion)
4. Build → Make Project (wait for "BUILD SUCCESSFUL")
```

**Why:** The C++ code in `audio_callback.h` has been fixed with thread-safe mutex protection.

### STEP 2: Restart Python Server

```powershell
# In terminal:
Ctrl + C  # Stop current server

# Wait 2 seconds

python main.py  # Restart
```

### STEP 3: Test on Device

```
1. Connect Android to server (IP:192.168.1.7:5101)
2. Play audio continuously
3. Keep connected for 10+ minutes
4. Watch Logcat for:
   ✅ "🔊 Audio recuperado" - Good
   ✅ "🗑️ Buffer saturado" occasional - Acceptable
   ❌ NO "Fatal signal 11" - Should NEVER appear
```

---

## What Was Fixed

**The Problem:**
- Thread 1 (network receiver) modifying `readPos` in drop logic
- Thread 2 (Oboe callback) reading `readPos` simultaneously
- Result: Corrupted memory → SIGSEGV crash

**The Solution:**
- Added mutex lock around all `readPos` access
- Made drop logic less aggressive (30% vs 50%)
- Prevents concurrent modification

**Code Changes:**
```cpp
// BEFORE (UNSAFE):
int newRP = (currentRP + ...) % bufferSize;
readPos.store(newRP);  // ❌ Race condition!

// AFTER (SAFE):
{
    std::lock_guard<std::mutex> lock(resetMutex);
    int newRP = (currentRP + ...) % bufferSize;
    readPos.store(newRP);  // ✅ Protected
}
```

---

## Expected Results

✅ **Audio will stay stable for 30+ minutes without crashing**
✅ **Occasional buffer saturation messages are OK**
✅ **No SIGSEGV crashes**
✅ **Audio plays smoothly**

---

## If Something Goes Wrong

**If app still crashes:**
1. Check that you recompiled (new build APK)
2. Check logcat for stack trace
3. Report the error and logcat output

**If audio has lag/stutter:**
1. This is separate from crash fix
2. Might need further buffer tuning
3. Report in new session

---

## Timeline

- **Phase 1:** Recompile app (5-10 min)
- **Phase 2:** Restart server (1 min)
- **Phase 3:** Test (10+ min)
- **Expected:** Stable audio, no crashes

---

**IMPORTANT:** Do NOT skip recompilation. The C++ code must be rebuilt for the fix to take effect.

Next message when you've completed: "Recompiled and tested"
