import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const outputDir = process.env.EVT_ACOUSTIC_DATA_OUTPUT || path.join(repoRoot, "hardware");
const previewDir = process.env.EVT_ACOUSTIC_PREVIEW_OUTPUT || path.join(repoRoot, "build", "acoustic_trade_study_rev_c_previews");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const navy = "#142A4A";
const headerBlue = "#245985";
const paleBlue = "#EAF1F7";
const border = "#B7C3CF";
const darkText = "#1F2937";
const bodyFont = "Arial";

const options = [
  {
    id: "BASELINE_T5838",
    structureRu: "4 x TDK T5838 MEMS, штатный массив",
    structureEn: "4 x TDK T5838 MEMS baseline array",
    effectRu: "Компактный когерентный захват и AAD",
    effectEn: "Compact coherent capture and AAD",
    band: "27-3000",
    noise: "26 dBA SPL EIN in high-quality mode; 68 dBA SNR",
    interface: "PDM",
    weatherRu: "Проверить штатную ветрозащиту и корпус в поле",
    weatherEn: "Verify the existing windshield and enclosure in the field",
    roleRu: "Базовый AAD и контрольный канал",
    roleEn: "Baseline AAD and reference channel",
    decision: "KEEP_BASELINE",
  },
  {
    id: "LOW_NOISE_MEMS",
    structureRu: "8-16 x Infineon IM73D122",
    structureEn: "8-16 x Infineon IM73D122",
    effectRu: "Ниже шум капсюля и больше пространственная апертура",
    effectEn: "Lower capsule noise and larger spatial aperture",
    band: "80-2000",
    noise: "73 dBA SNR; about 21 dBA SPL A-weighted input noise",
    interface: "PDM",
    weatherRu: "Корзинная ветрозащита и виброразвязка",
    weatherEn: "Full basket windshield and vibration isolation",
    roleRu: "Низкочастотный крупноапертурный массив",
    roleEn: "Low-frequency large-aperture array",
    decision: "PROTOTYPE_CANDIDATE",
  },
  {
    id: "ANALOG_MEMS",
    structureRu: "8-16 x Infineon IM73A135",
    structureEn: "8-16 x Infineon IM73A135",
    effectRu: "Низкий шум с дифференциальным аналоговым выходом",
    effectEn: "Low capsule noise with differential analog output",
    band: "80-2000",
    noise: "73 dBA SNR; 135 dBSPL AOP",
    interface: "Differential analog",
    weatherRu: "Корзинная защита и локальный малошумящий АЦП",
    weatherEn: "Full basket windshield and low-noise local ADC",
    roleRu: "Массив и канал сравнения резонаторов",
    roleEn: "Array and resonator comparison channel",
    decision: "PROTOTYPE_CANDIDATE",
  },
  {
    id: "SHOTGUN_NTG5",
    structureRu: "4-8 x RODE NTG5",
    structureEn: "4-8 x RODE NTG5",
    effectRu: "Направленность интерференционной трубки",
    effectEn: "Interference-tube directivity",
    band: "300-3000",
    noise: "10 dBA self-noise; 84 dB SNR",
    interface: "Balanced analog P48",
    weatherRu: "Профессиональная корзина, мех, дренаж, развязка мачты",
    weatherEn: "Professional basket, fur, drainage and mast isolation",
    roleRu: "Широкополосный направленный эталон",
    roleEn: "Broadband directional reference",
    decision: "PROTOTYPE_REFERENCE",
  },
  {
    id: "SHOTGUN_MKH416",
    structureRu: "4-8 x Sennheiser MKH 416",
    structureEn: "4-8 x Sennheiser MKH 416",
    effectRu: "Направленность трубки и RF condenser construction",
    effectEn: "Interference-tube directivity and RF condenser construction",
    band: "300-3000",
    noise: "13 dBA self-noise",
    interface: "Balanced analog P48",
    weatherRu: "Профессиональная корзина, мех, дренаж, развязка мачты",
    weatherEn: "Professional basket, fur, drainage and mast isolation",
    roleRu: "Защищенный кандидат сравнения",
    roleEn: "Rugged comparison candidate",
    decision: "PROTOTYPE_COMPARATOR",
  },
  {
    id: "CONICAL_HORN_700",
    structureRu: "Конический приемный рупор, раскрыв 0.7 m",
    structureEn: "0.7 m mouth conical receiving horn",
    effectRu: "Осесимметричное преобразование давления",
    effectEn: "Axisymmetric pressure transformation",
    band: "250-1500",
    noise: "Defined by capsule, throat and damping",
    interface: "Depends on capsule",
    weatherRu: "Контроль турбулентности, дренаж и защита горла",
    weatherEn: "Mouth turbulence control, drainage and throat windshield",
    roleRu: "Осесимметричный эталон рупора",
    roleEn: "Axisymmetric horn reference",
    decision: "BUILD_ONE",
  },
  {
    id: "PYRAMIDAL_HORN_800X500",
    structureRu: "Пирамидальный рупор 0.8 x 0.5 m",
    structureEn: "0.8 x 0.5 m pyramidal receiving horn",
    effectRu: "Раздельные горизонтальная и вертикальная апертуры",
    effectEn: "Separate horizontal and vertical aperture",
    band: "250-1500",
    noise: "Defined by capsule, throat and damping",
    interface: "Depends on capsule",
    weatherRu: "Обработка кромок, дренаж и защита горла",
    weatherEn: "Edge treatment, drainage and throat windshield",
    roleRu: "Первый кандидат секторного прототипа",
    roleEn: "Preferred sector prototype candidate",
    decision: "BUILD_ONE",
  },
  {
    id: "EXPONENTIAL_INSERT",
    structureRu: "Сменная экспоненциальная вставка рупора",
    structureEn: "Exchangeable exponential or near-exponential horn insert",
    effectRu: "Согласование импеданса в выбранной полосе",
    effectEn: "Improved acoustic impedance matching in a selected band",
    band: "300-1500",
    noise: "Defined by capsule, flare rate and throat",
    interface: "Depends on capsule",
    weatherRu: "Те же меры, что для рупора, плюс проверка высших мод",
    weatherEn: "Horn controls plus cutoff and higher-mode verification",
    roleRu: "Вставка после базового сравнения рупоров",
    roleEn: "Insert after base horn comparison",
    decision: "MODEL_THEN_BUILD",
  },
  {
    id: "PARABOLIC_600",
    structureRu: "Отражатель 0.6 m и малошумящий капсюль",
    structureEn: "0.6 m reflector with a low-noise capsule",
    effectRu: "Апертура с усилением, растущим с частотой",
    effectEn: "Aperture gain increasing with frequency",
    band: "500-3000",
    noise: "Defined by capsule and preamplifier",
    interface: "Depends on capsule",
    weatherRu: "Защита от порывов, дренаж, фазовая калибровка",
    weatherEn: "Gust shielding, drainage and phase calibration",
    roleRu: "Эксперимент физического усиления одного сектора",
    roleEn: "Single-sector physical gain experiment",
    decision: "BUILD_ONE",
  },
  {
    id: "TAPERED_RESONATOR_BANK",
    structureRu: "Кассета перекрывающихся сужающихся четвертьволновых каналов",
    structureEn: "Overlapping tapered quarter-wave cells",
    effectRu: "Узкополосное повышение давления до капсюля",
    effectEn: "Narrowband pressure gain before the capsule",
    band: "100-800",
    noise: "Defined by capsule, damping and Q",
    interface: "Depends on capsule",
    weatherRu: "Дренаж, защита от конденсата и механическое демпфирование",
    weatherEn: "Drainage, condensation control and mechanical damping",
    roleRu: "Вспомогательный гармонический канал",
    roleEn: "Auxiliary harmonic channel",
    decision: "BUILD_ONE",
  },
];

const targets = [
  ["SMALL_ELECTRIC_MULTIROTOR", "Малый электрический мультикоптер\nSmall electric multirotor", "Винты, электромоторы и регуляторы\nPropellers, motors and controllers", "Висение, ускорение, набор, пролет, удаление\nHover, acceleration, climb, pass, retreat", "Тональные линии и гармоники от низких сотен герц до нескольких килогерц\nTonal lines and harmonics from low hundreds of hertz to several kilohertz", "Калиброванный узкополосный и третьоктавный SPL на 1 m для каждого режима\nCalibrated narrowband and one-third-octave SPL at 1 m for every state", "MEASUREMENT_REQUIRED"],
  ["LARGE_ELECTRIC_AIRCRAFT", "Крупный электрический аппарат\nLarge electric aircraft", "Крупные винты, несколько приводов и поток\nLarge propellers, multiple drives and flow", "Взлет, набор, крейсер, маневр, снижение\nTakeoff, climb, cruise, maneuver, descent", "Низкие гармоники и среднечастотная гребенка\nLow harmonics and a mid-frequency tonal comb", "Спектр, геометрия, тяга и ракурс\nSpectrum, geometry, thrust state and aspect", "MEASUREMENT_REQUIRED"],
  ["PISTON_OR_ROTARY_COMBUSTION", "Поршневой или роторный аппарат\nPiston or rotary combustion aircraft", "Двигатель, выхлоп, редуктор, винт или ротор\nEngine, exhaust, gearbox, propeller or rotor", "Холостой ход, частичная и полная нагрузка, набор, крейсер\nIdle, partial and full load, climb, cruise", "Сильные низкие и средние гармоники и механический шум\nStrong low and mid harmonics with mechanical broadband energy", "Спектр, обороты, нагрузка и конфигурация выхлопа\nSpectrum, rotational speed, load and exhaust configuration", "MEASUREMENT_REQUIRED"],
  ["PROPELLER_FIXED_WING", "Винтовой самолет\nPropeller fixed wing", "Винт, двигатель и аэродинамический шум планера\nPropeller, engine and airframe flow", "Взлет, набор, крейсер, разворот, заход\nTakeoff, climb, cruise, turn, approach", "Частота прохождения лопастей и гармоники с зависимостью от ракурса\nBlade-passage components and aspect-dependent harmonics", "Спектр, дальность, высота, курс и скорость\nSpectrum, range, altitude, course and speed", "MEASUREMENT_REQUIRED"],
  ["TURBINE_OR_JET", "Турбинный или реактивный аппарат\nTurbine or jet", "Турбомашина и реактивная струя\nTurbomachinery and jet flow", "Малый газ, взлетная тяга, набор, крейсер, заход\nIdle, takeoff thrust, climb, cruise, approach", "Средне- и высокочастотный широкополосный шум с сильным атмосферным поглощением\nMid and high-frequency broadband components with strong air absorption", "Спектр и уровень для каждого режима двигателя\nSpectrum and level for every engine state", "MEASUREMENT_REQUIRED"],
  ["FALSE_SOURCE_SET", "Ложные источники\nFalse sources", "Транспорт, генераторы, механизмы, ветер и биофония\nVehicles, generators, machinery, wind and biological sources", "Условия конкретной площадки\nSite-specific operating states", "Перекрывающиеся тональные и широкополосные компоненты\nOverlapping tonal and broadband components", "Одновременная калиброванная запись фона на каждой площадке\nSimultaneous calibrated background recording at every site", "MEASUREMENT_REQUIRED"],
];

const rangeRows = [
  [100, 0.50],
  [160, 1.15],
  [250, 2.25],
  [400, 3.86],
  [630, 5.67],
  [1000, 8.15],
  [2000, 17.55],
  [4000, 53.19],
];

const tests = [
  ["LAB_RESPONSE", "Лабораторная АЧХ и фаза\nLaboratory response and phase", "АЧХ, собственный шум, диаграмма, фаза\nResponse, self-noise, pattern, phase", "80-3000 Hz; 12 azimuths; 3 levels", "Калибровочные файлы каждого канала\nPer-channel calibration files", "Полные данные по всем каналам\nComplete data for every channel", "PLANNED"],
  ["WIND_0_2", "Ветер 0-2 m/s\nWind 0-2 m/s", "Шум 20-500 Hz и импульсы\n20-500 Hz noise and impulses", "Одинаковая мачта и запись\nSame mast and recording", "WAV, ветер, конфигурация защиты\nWAV, wind and windshield configuration", "Нет клиппинга, измерен SNR\nNo clipping, SNR measured", "PLANNED"],
  ["WIND_2_5", "Ветер 2-5 m/s\nWind 2-5 m/s", "Шум 20-500 Hz и вибрация\n20-500 Hz noise and vibration", "Одинаковая мачта и запись\nSame mast and recording", "WAV, ветер, акселерометр при наличии\nWAV, wind and accelerometer if available", "Нет неопределенной вибрации\nNo unresolved vibration", "PLANNED"],
  ["WIND_5_8", "Ветер 5-8 m/s\nWind 5-8 m/s", "Порывы, клиппинг и устойчивость\nGusts, clipping and stability", "Только безопасная утвержденная установка\nApproved safe setup only", "WAV, ветер, фото и состояние\nWAV, wind, photographs and condition", "Нет повреждения или клиппинга\nNo damage or clipping", "PLANNED"],
  ["RANGE_SERIES", "Дистанционная серия\nRange series", "Сырой узкополосный SNR\nRaw narrowband SNR", "50, 100, 250, 500, 1000, 2000 m", "Геометрия, погода, трек и WAV\nGeometry, weather, track and WAV", "Результат отдельно по классу и режиму\nResult by class and state", "PLANNED"],
  ["TARGET_CLASSES", "Реальные классы целей\nReal target classes", "Обнаружение, пропуски, ракурс и режим\nDetection, misses, aspect and state", "Все классы плюс фон\nAll classes plus background", "Pd, FAR, SNR и условия\nPd, FAR, SNR and conditions", "Pd и FAR утверждены до заявления дальности\nPd and FAR approved before range claim", "PLANNED"],
  ["SIMULTANEOUS_COMPARE", "Одновременное сравнение\nSimultaneous comparison", "T5838, shotgun, рупоры, отражатель, резонаторы\nT5838, shotgun, horns, reflector, resonators", "Одна мачта, одно время, один алгоритм\nOne mast, time and algorithm", "Синхронные WAV и калибровка\nSynchronous WAV and calibration", "Физический выигрыш без отдельной настройки\nPhysical gain without separate tuning", "PLANNED"],
  ["INTEGRATION_GATE", "Шлюз интеграции\nIntegration gate", "Питание, интерфейс, защита, механика\nPower, interface, protection, mechanics", "После выбора физической головки\nAfter physical-head selection", "ICD, ECO и перечень проверок\nICD, ECO and verification list", "Серийные платы не меняются без ECO\nNo production-board change without ECO", "PLANNED"],
];

const sources = [
  ["S01", "TDK InvenSense T5838 product page and DS-000383 datasheet", "https://www.invensense.tdk.com/en-us/products/microphone/t5838", "Baseline microphone"],
  ["S02", "Infineon IM73D122 product data", "https://www.infineon.com/part/IM73D122", "Low-noise digital MEMS"],
  ["S03", "Infineon IM73A135 datasheet", "https://www.infineon.com/assets/row/public/documents/24/49/infineon-im73a135-datasheet-en.pdf", "Low-noise analog MEMS"],
  ["S04", "RODE NTG5 specifications", "https://rode.com/en-us/products/ntg5", "Directional reference microphone"],
  ["S05", "Sennheiser MKH 416 specifications", "https://docs.cloud.sennheiser.com/en-us/mkh-416-mkh-418-s/specs-mkh-416.html", "Directional comparator"],
  ["S06", "Outdoor Microphone Range Tests and Spectral Analysis of UAV Acoustic Signatures", "https://pmc.ncbi.nlm.nih.gov/articles/PMC12656299/", "Outdoor UAV acoustic measurement"],
  ["S07", "NASA atmospheric propagation relation and absorption discussion", "https://ntrs.nasa.gov/api/citations/19750024046/downloads/19750024046.pdf", "Propagation basis"],
  ["S08", "The response of Helmholtz resonator to external excitation", "https://acoustics.ippt.pan.pl/index.php/aa/article/view/471", "Resonator behavior"],
  ["S09", "Characterization of gain and directivity of exponential horn receivers", "https://www.engr.colostate.edu/~notaros/Papers/JASA_Acoustic_Horns.pdf", "Horn receivers"],
  ["S10", "Monaural sound localization based on structure-induced acoustic resonance", "https://pubmed.ncbi.nlm.nih.gov/25668214/", "Pyramidal resonance and localization"],
  ["S11", "Assembling cheap high-performance microphones for recording terrestrial wildlife", "https://f1000research.com/articles/7-1984", "Horn measurement example"],
];

function writeTitle(sheet, title, subtitle, lastColumn) {
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: bodyFont, size: 14, bold: true, color: navy };
  sheet.getRange("A3").values = [[subtitle]];
  sheet.getRange("A3").format.font = { name: bodyFont, size: 10, italic: true, color: "#555555" };
  sheet.getRange(`A4:${lastColumn}4`).format.borders = { bottom: { style: "thin", color: "#4F81BD" } };
}

function formatTable(sheet, rangeAddress, headerAddress, bodyAddress) {
  const full = sheet.getRange(rangeAddress);
  full.format.font = { name: bodyFont, size: 9, color: darkText };
  full.format.verticalAlignment = "center";
  full.format.wrapText = true;
  full.format.borders = { preset: "all", style: "thin", color: border };
  const header = sheet.getRange(headerAddress);
  header.format.fill = headerBlue;
  header.format.font = { name: bodyFont, size: 9, bold: true, color: "#FFFFFF" };
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  if (bodyAddress) {
    const body = sheet.getRange(bodyAddress);
    body.format.verticalAlignment = "center";
  }
}

function shadeAlternateRows(sheet, startRow, endRow, lastColumn) {
  for (let row = startRow; row <= endRow; row += 2) {
    sheet.getRange(`A${row}:${lastColumn}${row}`).format.fill = paleBlue;
  }
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\r\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

async function writeCsv(fileName, headers, rows) {
  const lines = [headers, ...rows].map((row) => row.map(csvEscape).join(","));
  await fs.writeFile(path.join(outputDir, fileName), lines.join("\r\n") + "\r\n", "utf8");
}

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Сводка Summary");
const optionsSheet = workbook.worksheets.add("Варианты Options");
const targetsSheet = workbook.worksheets.add("Цели Targets");
const rangeSheet = workbook.worksheets.add("Расчет Range");
const testsSheet = workbook.worksheets.add("Испытания Tests");
const sourcesSheet = workbook.worksheets.add("Источники Sources");

summary.tabColor = navy;
optionsSheet.tabColor = "#4F81BD";
targetsSheet.tabColor = "#6C8EBF";
rangeSheet.tabColor = "#9EADBF";
testsSheet.tabColor = "#B4C7E7";
sourcesSheet.tabColor = "#A6A6A6";

writeTitle(summary, "Акустический тракт LR-1 EVT-PRE-20", "Controlled bilingual engineering evaluation, Rev C, 27.10.2026", "H");
summary.getRange("A6:B11").values = [
  ["Параметр / Parameter", "Значение / Value"],
  ["Производственный baseline / Production baseline", "4 x TDK T5838, KEEP_BASELINE"],
  ["Статус LR-1 / LR-1 status", "EXPERIMENTAL PARALLEL MODULE"],
  ["Вариантов BUILD_ONE / BUILD_ONE options", null],
  ["Классов целей / Target classes", null],
  ["Максимальная дистанция серии / Maximum test range m", null],
];
summary.getRange("B9").formulas = [["=COUNTIFS('Варианты Options'!$I$6:$I$15,\"BUILD_ONE\")"]];
summary.getRange("B10").formulas = [["=COUNTA('Цели Targets'!$A$6:$A$11)"]];
summary.getRange("B11").formulas = [["=MAX('Расчет Range'!$A$6:$A$13)"]];
formatTable(summary, "A6:B11", "A6:B6", "A7:B11");
summary.getRange("A13:D18").values = [
  ["Полоса / Band", "Физический тракт / Physical path", "Назначение / Purpose", "Решение / Decision"],
  ["80-400 Hz", "Массив 1.2-2 m / 1.2-2 m array", "Низкочастотная апертура / Low-frequency aperture", "PROTOTYPE"],
  ["250-1500 Hz", "Конический и пирамидальный рупоры / Conical and pyramidal horns", "Секторное сравнение / Sector comparison", "BUILD_ONE_EACH"],
  ["300-3000 Hz", "Shotgun reference", "Направленный эталон / Directional reference", "COMPARE"],
  ["500-3000 Hz", "Отражатель 0.6 m / 0.6 m reflector", "Физическое усиление сектора / Sector aperture gain", "BUILD_ONE"],
  ["100-800 Hz", "Кассета резонаторов / Resonator bank", "Вспомогательные гармоники / Auxiliary harmonics", "BUILD_ONE"],
];
formatTable(summary, "A13:D18", "A13:D13", "A14:D18");
summary.getRange("A20:D23").values = [
  ["Контроль / Control", "Требование / Requirement", "Статус / Status", "Действие / Action"],
  ["2 km claim", "Источник, погода, Pd и FAR должны быть зафиксированы / Source, weather, Pd and FAR must be fixed", "OPEN", "Field measurements"],
  ["Production baseline", "PCB-MAIN, PCB-PWR and PCB-MIC unchanged", "LOCKED", "ECO before any change"],
  ["Revision lineage", "Rev A and Rev B retained", "COMPLETE", "Use Rev C as current study"],
];
formatTable(summary, "A20:D23", "A20:D20", "A21:D23");
summary.getRange("A2:H23").format.font.name = bodyFont;
summary.getRange("A:A").format.columnWidth = 34;
summary.getRange("B:B").format.columnWidth = 54;
summary.getRange("C:C").format.columnWidth = 31;
summary.getRange("D:D").format.columnWidth = 27;
summary.freezePanes.freezeRows(4);

writeTitle(optionsSheet, "Варианты физической акустической головки", "Physical acoustic-head options, Rev C", "I");
const optionHeaders = ["ID", "Конструкция / Structure", "Физический эффект / Physical effect", "Полоса Hz", "Шум или SNR / Noise or SNR", "Интерфейс / Interface", "Погода и ветер / Weather and wind", "Роль / Role", "Решение / Decision"];
const optionRows = options.map((item) => [
  item.id,
  `${item.structureRu}\n${item.structureEn}`,
  `${item.effectRu}\n${item.effectEn}`,
  item.band,
  item.noise,
  item.interface,
  `${item.weatherRu}\n${item.weatherEn}`,
  `${item.roleRu}\n${item.roleEn}`,
  item.decision,
]);
optionsSheet.getRange(`A5:I${5 + optionRows.length}`).values = [optionHeaders, ...optionRows];
formatTable(optionsSheet, `A5:I${5 + optionRows.length}`, "A5:I5", `A6:I${5 + optionRows.length}`);
shadeAlternateRows(optionsSheet, 7, 5 + optionRows.length, "I");
optionsSheet.getRange("A:A").format.columnWidth = 24;
optionsSheet.getRange("B:C").format.columnWidth = 31;
optionsSheet.getRange("D:D").format.columnWidth = 13;
optionsSheet.getRange("E:E").format.columnWidth = 26;
optionsSheet.getRange("F:F").format.columnWidth = 20;
optionsSheet.getRange("G:H").format.columnWidth = 32;
optionsSheet.getRange("I:I").format.columnWidth = 23;
optionsSheet.freezePanes.freezeRows(5);

writeTitle(targetsSheet, "Классы акустических целей", "Target classes and required source measurements, Rev B", "G");
const targetHeaders = ["ID", "Класс / Class", "Источник / Source", "Режимы / States", "Признаки / Features", "Обязательное измерение / Required measurement", "Статус / Status"];
targetsSheet.getRange(`A5:G${5 + targets.length}`).values = [targetHeaders, ...targets];
formatTable(targetsSheet, `A5:G${5 + targets.length}`, "A5:G5", `A6:G${5 + targets.length}`);
shadeAlternateRows(targetsSheet, 7, 5 + targets.length, "G");
targetsSheet.getRange("A:A").format.columnWidth = 28;
targetsSheet.getRange("B:B").format.columnWidth = 28;
targetsSheet.getRange("C:F").format.columnWidth = 34;
targetsSheet.getRange("G:G").format.columnWidth = 24;
targetsSheet.freezePanes.freezeRows(5);

writeTitle(rangeSheet, "Расчет потерь на 2 км", "15 °C, 70 percent RH, 101.325 kPa; free-field estimate", "J");
const rangeHeaders = ["Частота Hz", "Поглощение dB", "Расхождение dB", "Полные потери dB", "Источник 70 dB", "Прием 70 dB", "Источник 85 dB", "Прием 85 dB", "Источник 100 dB", "Прием 100 dB"];
rangeSheet.getRange("A5:J5").values = [rangeHeaders];
rangeSheet.getRange("A6:B13").values = rangeRows;
rangeSheet.getRange("C6:C13").values = rangeRows.map(() => [66.02]);
rangeSheet.getRange("D6").formulas = [["=B6+C6"]];
rangeSheet.getRange("D6:D13").fillDown();
rangeSheet.getRange("E6:E13").values = rangeRows.map(() => [70]);
rangeSheet.getRange("F6").formulas = [["=E6-D6"]];
rangeSheet.getRange("F6:F13").fillDown();
rangeSheet.getRange("G6:G13").values = rangeRows.map(() => [85]);
rangeSheet.getRange("H6").formulas = [["=G6-D6"]];
rangeSheet.getRange("H6:H13").fillDown();
rangeSheet.getRange("I6:I13").values = rangeRows.map(() => [100]);
rangeSheet.getRange("J6").formulas = [["=I6-D6"]];
rangeSheet.getRange("J6:J13").fillDown();
formatTable(rangeSheet, "A5:J13", "A5:J5", "A6:J13");
shadeAlternateRows(rangeSheet, 7, 13, "J");
rangeSheet.getRange("A6:A13").format.numberFormat = "0";
rangeSheet.getRange("B6:J13").format.numberFormat = "0.00";
rangeSheet.getRange("A:J").format.columnWidth = 18;
rangeSheet.getRange("A15:J16").values = [
  ["Примечание / Note", "Уровни 70, 85 и 100 dB SPL являются сценариями, а не присвоенными классам целям / The 70, 85 and 100 dB SPL levels are scenarios, not class assignments", null, null, null, null, null, null, null, null],
  ["Ограничение / Limitation", "Не учтены земля, препятствия, ветер, температурный градиент и теневые зоны / Ground, obstructions, wind, temperature gradients and shadow zones are excluded", null, null, null, null, null, null, null, null],
];
rangeSheet.mergeCells("B15:J15");
rangeSheet.mergeCells("B16:J16");
rangeSheet.getRange("A15:J16").format.font = { name: bodyFont, size: 9, color: darkText };
rangeSheet.getRange("A15:J16").format.wrapText = true;
rangeSheet.getRange("A15:A16").format.font = { name: bodyFont, size: 9, bold: true, color: navy };
rangeSheet.getRange("A15:J16").format.rowHeight = 28;
rangeSheet.freezePanes.freezeRows(5);

writeTitle(testsSheet, "Матрица проверки LR-1", "Physical verification matrix, Rev A", "G");
const testHeaders = ["ID", "Этап / Stage", "Измерение / Measurement", "Условия / Conditions", "Доказательство / Evidence", "Критерий / Criterion", "Статус / Status"];
testsSheet.getRange(`A5:G${5 + tests.length}`).values = [testHeaders, ...tests];
formatTable(testsSheet, `A5:G${5 + tests.length}`, "A5:G5", `A6:G${5 + tests.length}`);
shadeAlternateRows(testsSheet, 7, 5 + tests.length, "G");
testsSheet.getRange("A:A").format.columnWidth = 25;
testsSheet.getRange("B:F").format.columnWidth = 32;
testsSheet.getRange("G:G").format.columnWidth = 18;
testsSheet.getRange(`G6:G${5 + tests.length}`).conditionalFormats.addCustom('=G6="PLANNED"', { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } });
testsSheet.freezePanes.freezeRows(5);

writeTitle(sourcesSheet, "Источники", "Primary and manufacturer sources used in Rev C", "D");
sourcesSheet.getRange(`A5:D${5 + sources.length}`).values = [["ID", "Источник / Source", "URL", "Использование / Use"], ...sources];
formatTable(sourcesSheet, `A5:D${5 + sources.length}`, "A5:D5", `A6:D${5 + sources.length}`);
shadeAlternateRows(sourcesSheet, 7, 5 + sources.length, "D");
sourcesSheet.getRange("A:A").format.columnWidth = 10;
sourcesSheet.getRange("B:B").format.columnWidth = 58;
sourcesSheet.getRange("C:C").format.columnWidth = 74;
sourcesSheet.getRange("D:D").format.columnWidth = 30;
sourcesSheet.freezePanes.freezeRows(5);

workbook.recalculate();

const summaryCheck = await workbook.inspect({
  kind: "table",
  range: "Сводка Summary!A6:D23",
  include: "values,formulas",
  tableMaxRows: 24,
  tableMaxCols: 8,
});
console.log(summaryCheck.ndjson);

const rangeCheck = await workbook.inspect({
  kind: "table",
  range: "Расчет Range!A5:J13",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 12,
});
console.log(rangeCheck.ndjson);

const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errorCheck.ndjson);

for (const sheetName of ["Сводка Summary", "Варианты Options", "Цели Targets", "Расчет Range", "Испытания Tests", "Источники Sources"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.2, format: "png" });
  const safeName = sheetName.replaceAll(" ", "_");
  await fs.writeFile(path.join(previewDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(path.join(outputDir, "EVT_PRE_20_ACOUSTIC_TRADE_STUDY_REV_C.xlsx"));

await writeCsv(
  "EVT_PRE_20_ACOUSTIC_HEAD_ALTERNATIVES_REV_C.csv",
  ["option_id", "transducer_or_structure", "primary_physical_effect", "initial_design_band_hz", "self_noise_or_snr", "interface", "weathering_or_wind_requirement", "proposed_role", "decision_status"],
  options.map((item) => [item.id, item.structureEn, item.effectEn, item.band, item.noise, item.interface, item.weatherEn, item.roleEn, item.decision]),
);
await writeCsv(
  "EVT_PRE_20_ACOUSTIC_TARGET_CLASSES_REV_B.csv",
  ["target_class", "class_description", "propulsion_or_source", "operating_states", "physical_search_features", "required_reference_measurement", "range_claim_status"],
  targets.map((row) => [row[0], row[1].split("\n")[1], row[2].split("\n")[1], row[3].split("\n")[1], row[4].split("\n")[1], row[5].split("\n")[1], row[6]]),
);
await writeCsv(
  "EVT_PRE_20_ACOUSTIC_RANGE_BUDGET_2KM_REV_A.csv",
  ["frequency_hz", "atmospheric_absorption_db", "geometric_spreading_db", "total_propagation_loss_db", "received_70db_source_db_spl", "received_85db_source_db_spl", "received_100db_source_db_spl"],
  rangeRows.map(([frequency, absorption]) => {
    const total = absorption + 66.02;
    return [frequency, absorption.toFixed(2), "66.02", total.toFixed(2), (70 - total).toFixed(2), (85 - total).toFixed(2), (100 - total).toFixed(2)];
  }),
);
await writeCsv(
  "EVT_PRE_20_LR1_PHYSICAL_TEST_MATRIX_REV_A.csv",
  ["test_id", "stage", "measurement", "conditions", "required_evidence", "pass_or_hold_criterion", "status"],
  tests.map((row) => [row[0], row[1].split("\n")[1], row[2].split("\n")[1], row[3].split("\n").at(-1), row[4].split("\n")[1], row[5].split("\n")[1], row[6]]),
);

console.log(path.join(outputDir, "EVT_PRE_20_ACOUSTIC_TRADE_STUDY_REV_C.xlsx"));
