/*
 * EVT-PRE-20 Rev.A engineering linker script for STM32U585VIT6Q.
 *
 * Memory geometry is derived from ST DS13086 Rev 10 and the STM32CubeU5
 * v1.9.0 STM32U585xI GCC linker template. This full-flash layout is for
 * hardware bring-up only. It is not the secure-boot/A-B production layout.
 */

ENTRY(Reset_Handler)

_Min_Heap_Size = 0x400;
_Min_Stack_Size = 0x2000;

MEMORY
{
  FLASH  (rx)  : ORIGIN = 0x08000000, LENGTH = 2048K
  RAM123 (xrw) : ORIGIN = 0x20000000, LENGTH = 768K
  SRAM4  (xrw) : ORIGIN = 0x28000000, LENGTH = 16K
}

_estack = ORIGIN(RAM123) + LENGTH(RAM123);
_sstack = _estack - _Min_Stack_Size;

SECTIONS
{
  .isr_vector : ALIGN(512)
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .text :
  {
    *(.text)
    *(.text*)
    *(.glue_7)
    *(.glue_7t)
    *(.eh_frame)
    KEEP(*(.init))
    KEEP(*(.fini))
    _etext = .;
  } > FLASH

  .rodata :
  {
    *(.rodata)
    *(.rodata*)
  } > FLASH

  .ARM.extab :
  {
    *(.ARM.extab* .gnu.linkonce.armextab.*)
  } > FLASH

  .ARM :
  {
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
  } > FLASH

  .preinit_array :
  {
    PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array*))
    PROVIDE_HIDDEN(__preinit_array_end = .);
  } > FLASH

  .init_array :
  {
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT(.init_array.*)))
    KEEP(*(.init_array*))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > FLASH

  .fini_array :
  {
    PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT(.fini_array.*)))
    KEEP(*(.fini_array*))
    PROVIDE_HIDDEN(__fini_array_end = .);
  } > FLASH

  _sidata = LOADADDR(.data);

  .data : ALIGN(8)
  {
    _sdata = .;
    *(.data)
    *(.data*)
    *(.RamFunc)
    *(.RamFunc*)
    _edata = .;
  } > RAM123 AT> FLASH

  .bss (NOLOAD) : ALIGN(8)
  {
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss)
    *(.bss*)
    *(COMMON)
    _ebss = .;
    __bss_end__ = _ebss;
  } > RAM123

  .retained (NOLOAD) : ALIGN(8)
  {
    /* Link placement only. PWR retention must be configured and measured. */
    _sretained = .;
    *(.retained)
    *(.retained*)
    _eretained = .;
  } > SRAM4

  .heap_stack (NOLOAD) : ALIGN(8)
  {
    PROVIDE(end = .);
    PROVIDE(_end = .);
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } > RAM123

  .ARM.attributes 0 : { *(.ARM.attributes) }
}

ASSERT(SIZEOF(.isr_vector) > 0, "missing STM32U585 interrupt vector");
ASSERT(_eretained <= ORIGIN(SRAM4) + LENGTH(SRAM4), "SRAM4 retained area overflow");
ASSERT(_end <= _sstack, "RAM123 heap/stack collision");
