// Minimal offline AU host for measurements.
//
//   auhost <type> <subtype> <manu> <sr> <block> <in.f32> <out.f32> [id=value ...]
//
// in.f32: interleaved stereo float32 (L,R). out.f32 same layout.
// Prints parameter info and the average render time per block.
// Build: clang -O2 -arch x86_64 -arch arm64 -framework AudioToolbox
//        -framework CoreFoundation tools/auhost.c -o auhost
#include <AudioToolbox/AudioToolbox.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float *g_in;
static long g_frames, g_pos;

static OSStatus input_cb(void *ref, AudioUnitRenderActionFlags *flags, const AudioTimeStamp *ts,
                         UInt32 bus, UInt32 n, AudioBufferList *io) {
    float *l = io->mBuffers[0].mData;
    float *r = io->mNumberBuffers > 1 ? io->mBuffers[1].mData : NULL;
    for (UInt32 i = 0; i < n; i++) {
        long k = g_pos + i;
        float a = k < g_frames ? g_in[2 * k] : 0.f, b = k < g_frames ? g_in[2 * k + 1] : 0.f;
        l[i] = a;
        if (r) r[i] = b;
    }
    return noErr;
}

static OSType fourcc(const char *s) { return ((OSType)s[0] << 24) | (s[1] << 16) | (s[2] << 8) | s[3]; }

#define CHECK(x) do { OSStatus e_ = (x); if (e_) { fprintf(stderr, "%s failed: %d\n", #x, (int)e_); return 1; } } while (0)

int main(int argc, char **argv) {
    if (argc < 8) { fprintf(stderr, "usage\n"); return 2; }
    AudioComponentDescription d = {fourcc(argv[1]), fourcc(argv[2]), fourcc(argv[3]), 0, 0};
    double sr = atof(argv[4]);
    UInt32 block = atoi(argv[5]);
    AudioComponent c = AudioComponentFindNext(NULL, &d);
    if (!c) { fprintf(stderr, "component not found\n"); return 1; }
    AudioUnit au;
    CHECK(AudioComponentInstanceNew(c, &au));

    AudioStreamBasicDescription f = {0};
    f.mSampleRate = sr; f.mFormatID = kAudioFormatLinearPCM;
    f.mFormatFlags = kAudioFormatFlagsNativeFloatPacked | kAudioFormatFlagIsNonInterleaved;
    f.mBytesPerPacket = 4; f.mFramesPerPacket = 1; f.mBytesPerFrame = 4;
    f.mChannelsPerFrame = 2; f.mBitsPerChannel = 32;
    CHECK(AudioUnitSetProperty(au, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &f, sizeof f));
    CHECK(AudioUnitSetProperty(au, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Output, 0, &f, sizeof f));
    CHECK(AudioUnitSetProperty(au, kAudioUnitProperty_MaximumFramesPerSlice, kAudioUnitScope_Global, 0, &block, sizeof block));
    AURenderCallbackStruct cb = {input_cb, NULL};
    CHECK(AudioUnitSetProperty(au, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &cb, sizeof cb));
    CHECK(AudioUnitInitialize(au));

    // Parameter listing
    UInt32 sz = 0;
    AudioUnitGetPropertyInfo(au, kAudioUnitProperty_ParameterList, kAudioUnitScope_Global, 0, &sz, NULL);
    AudioUnitParameterID ids[64];
    if (sz > sizeof ids) sz = sizeof ids;
    AudioUnitGetProperty(au, kAudioUnitProperty_ParameterList, kAudioUnitScope_Global, 0, ids, &sz);
    for (UInt32 i = 0; i < sz / sizeof(AudioUnitParameterID); i++) {
        AudioUnitParameterInfo pi; UInt32 s2 = sizeof pi; AudioUnitParameterValue v = 0;
        AudioUnitGetProperty(au, kAudioUnitProperty_ParameterInfo, kAudioUnitScope_Global, ids[i], &pi, &s2);
        AudioUnitGetParameter(au, ids[i], kAudioUnitScope_Global, 0, &v);
        char name[128] = "?";
        if (pi.cfNameString) CFStringGetCString(pi.cfNameString, name, sizeof name, kCFStringEncodingUTF8);
        fprintf(stderr, "param %u '%s' [%g..%g] default %g current %g\n", (unsigned)ids[i], name,
                pi.minValue, pi.maxValue, pi.defaultValue, v);
    }
    for (int a = 8; a < argc; a++) {
        unsigned id; float v;
        if (sscanf(argv[a], "%u=%f", &id, &v) == 2)
            CHECK(AudioUnitSetParameter(au, id, kAudioUnitScope_Global, 0, v, 0));
    }
    Float64 lat = 0; UInt32 ls = sizeof lat;
    AudioUnitGetProperty(au, kAudioUnitProperty_Latency, kAudioUnitScope_Global, 0, &lat, &ls);
    fprintf(stderr, "latency %g s (%.1f samples)\n", lat, lat * sr);

    FILE *fi = fopen(argv[6], "rb");
    if (!fi) { perror("in"); return 1; }
    fseek(fi, 0, SEEK_END); long bytes = ftell(fi); fseek(fi, 0, SEEK_SET);
    g_frames = bytes / 8;
    g_in = malloc(bytes);
    fread(g_in, 1, bytes, fi); fclose(fi);
    float *out = calloc(g_frames * 2, sizeof(float));

    float *bl = malloc(block * 4), *br = malloc(block * 4);
    AudioBufferList *abl = malloc(sizeof(AudioBufferList) + sizeof(AudioBuffer));
    AudioTimeStamp ts = {0}; ts.mFlags = kAudioTimeStampSampleTimeValid;
    mach_timebase_info_data_t tb; mach_timebase_info(&tb);
    double worst = 0, total = 0; long blocks = 0;
    for (g_pos = 0; g_pos < g_frames; g_pos += block) {
        UInt32 n = (UInt32)((g_frames - g_pos) < block ? (g_frames - g_pos) : block);
        abl->mNumberBuffers = 2;
        abl->mBuffers[0] = (AudioBuffer){1, n * 4, bl};
        abl->mBuffers[1] = (AudioBuffer){1, n * 4, br};
        AudioUnitRenderActionFlags fl = 0;
        ts.mSampleTime = g_pos;
        uint64_t t0 = mach_absolute_time();
        CHECK(AudioUnitRender(au, &fl, &ts, 0, n, abl));
        double us = (mach_absolute_time() - t0) * (double)tb.numer / tb.denom / 1000.0;
        total += us; blocks++; if (us > worst) worst = us;
        for (UInt32 i = 0; i < n; i++) {
            out[2 * (g_pos + i)] = ((float *)abl->mBuffers[0].mData)[i];
            out[2 * (g_pos + i) + 1] = ((float *)abl->mBuffers[1].mData)[i];
        }
    }
    double budget = block / sr * 1e6;
    fprintf(stderr, "render: avg %.1f us, worst %.1f us per %u-frame block (budget %.0f us) -> avg %.1f%% / worst %.1f%% of real time\n",
            total / blocks, worst, block, budget, 100 * total / blocks / budget, 100 * worst / budget);
    FILE *fo = fopen(argv[7], "wb");
    fwrite(out, sizeof(float), g_frames * 2, fo); fclose(fo);
    AudioUnitUninitialize(au);
    AudioComponentInstanceDispose(au);
    return 0;
}
