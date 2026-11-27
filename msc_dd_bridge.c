// msc_dd_bridge.c — Core command & raw SCSI block-write handler (stack-agnostic C skeleton)
// Wire tuh_msc_read10 / tuh_msc_write10 (TinyUSB) or your USB Host MSC SCSI layer to write_lba().

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SECTOR_SIZE 512u
#define MAX_CHUNK_BLOCKS 8u  // 4 KiB per transfer chunk to keep MCU RAM predictable

static uint32_t current_lba = 0;
static uint32_t drive_blocks = 0;
static bool drive_ready = false;

// Replace these two hooks with your USB Host MSC driver calls:
// e.g. TinyUSB tuh_msc_write10(dev_addr, lun, buffer, lba, block_count, cb, arg)
extern bool host_msc_get_capacity(uint32_t *out_blocks, uint32_t *out_sec_size);
extern bool host_msc_write_sectors(uint32_t lba, uint16_t count, const uint8_t *buf);
extern bool host_msc_sync_cache(void);

// Replace with your control serial/CDC TX and exact-byte RX routines:
extern void ctrl_println(const char *s);
extern bool ctrl_read_exact(uint8_t *dst, size_t len);

static void handle_info(void) {
    uint32_t blocks = 0, sec_sz = 0;
    if (!host_msc_get_capacity(&blocks, &sec_sz) || sec_sz == 0) {
        drive_ready = false;
        ctrl_println("ERR NO_MSC_DRIVE");
        return;
    }
    drive_blocks = blocks;
    drive_ready = true;
    char out[96];
    snprintf(out, sizeof(out), "OK BLOCKS=%lu SEC_SIZE=%lu",
             (unsigned long)drive_blocks, (unsigned long)sec_sz);
    ctrl_println(out);
}

static void handle_seek(const char *arg) {
    uint32_t lba = (uint32_t)strtoul(arg, NULL, 10);
    if (drive_ready && lba >= drive_blocks) {
        ctrl_println("ERR LBA_OUT_OF_RANGE");
        return;
    }
    current_lba = lba;
    char out[64];
    snprintf(out, sizeof(out), "OK LBA=%lu", (unsigned long)current_lba);
    ctrl_println(out);
}

static void handle_write_blocks(const char *arg) {
    uint32_t count = (uint32_t)strtoul(arg, NULL, 10);
    if (!drive_ready) {
        ctrl_println("ERR DRIVE_NOT_READY");
        return;
    }
    if (count == 0 || count > MAX_CHUNK_BLOCKS) {
        ctrl_println("ERR BAD_BLOCK_COUNT");
        return;
    }
    if (current_lba + count > drive_blocks) {
        ctrl_println("ERR WRITE_PAST_EOF");
        return;
    }

    uint8_t sector_buf[MAX_CHUNK_BLOCKS * SECTOR_SIZE];
    size_t total_bytes = (size_t)count * SECTOR_SIZE;

    ctrl_println("READY");
    if (!ctrl_read_exact(sector_buf, total_bytes)) {
        ctrl_println("ERR SERIAL_TIMEOUT");
        return;
    }

    if (!host_msc_write_sectors(current_lba, (uint16_t)count, sector_buf)) {
        ctrl_println("ERR SCSI_WRITE10_FAIL");
        return;
    }

    current_lba += count;
    ctrl_println("OK");
}

void bridge_process_line(char *line) {
    while (*line == ' ' || *line == '\r' || *line == '\n') line++;
    size_t len = strlen(line);
    while (len > 0 && (line[len - 1] == '\r' || line[len - 1] == '\n' || line[len - 1] == ' ')) {
        line[--len] = '\0';
    }
    if (len == 0) return;

    if (strcmp(line, "INFO") == 0) {
        handle_info();
    } else if (strncmp(line, "SEEK ", 5) == 0) {
        handle_seek(line + 5);
    } else if (strncmp(line, "WRITE_BLOCKS ", 13) == 0) {
        handle_write_blocks(line + 13);
    } else if (strcmp(line, "FLUSH") == 0) {
        if (host_msc_sync_cache()) {
            ctrl_println("OK FLUSHED");
        } else {
            ctrl_println("ERR FLUSH_FAIL");
        }
    } else {
        ctrl_println("ERR UNKNOWN_CMD");
    }
}
