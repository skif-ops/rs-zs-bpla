# Извещение о вариантах закупки EVT PRE 20 REV D8

Документ фиксирует объём программы EVT PRE 20 и два допустимых варианта закупочной выдачи. Он предназначен для заказчика, отдела закупки, изготовителей и сборочного участка. Программа испытаний включает 41 станцию. Вариант закупки на 21 станцию является первой фазой и не изменяет состав программы или ранее выпущенный реестр серийных номеров.

## Управляющее решение

Программа EVT состоит из двух групп по 20 станций и одной стендовой станции. Зарезервированы 41 уникальный серийный номер: DIO-EVT-001 по DIO-EVT-040 и DIO-EVT-B01.

## Источники количества и BOM

Реестр вариантов находится в hardware/EVT_PROGRAM_PROCUREMENT_VARIANTS_REV_A.csv. Итоговая книга hardware/EVT_PRE_20_BOM_REV_A.xlsx содержит отдельные листы Program 21 и Program 41, а также сводную строку выбора. Машиночитаемые CSV являются источниками количества, книга XLSX предназначена для просмотра, расчёта и передачи в закупку.

## EOL и измерения

Каждая собранная станция проходит стопроцентный EOL с привязкой к собственному серийному номеру. Число 21 в строке OPEN criteria формы MFG 004 означает количество открытых критериев приёмки, а не количество станций. Окончательные числовые пределы EOL утверждаются по измерениям DIO-EVT-B01 и последующих собранных станций. Пока обязательный предел или подтверждение отсутствуют, результат остаётся HOLD или NOT RUN.

## English version

This notice fixes the EVT PRE 20 program quantity and the two permitted procurement handoffs. The EVT program contains 41 stations: two groups of 20 production stations and one bench station. Forty-one unique serial identities are reserved from DIO-EVT-001 through DIO-EVT-040 plus DIO-EVT-B01.

The customer selects exactly one option for a purchase order. Quantities for 21 and 41 are not added together. Selecting 21 is a phased first purchase and does not cancel the serial reservation for DIO-EVT-021 through DIO-EVT-040.

The controlled workbook hardware/EVT_PRE_20_BOM_REV_A.xlsx contains separate Program 21 and Program 41 worksheets and a summary selection row. Every assembled station receives 100 percent EOL against its own serial identity. The value 21 shown as OPEN criteria in the MFG 004 form is a count of unresolved acceptance criteria and is not the station quantity. Final numeric EOL limits remain open until measurements from DIO-EVT-B01 and subsequent assembled stations are reviewed and approved.

## Управление выпуском и подписи

Решение: DEC-148 от 16 октября 2026 года. Ревизия документа: D8. Статус: подготовлено для выбора варианта закупки; изготовление остаётся под действием указанных в комплекте технических ворот.
