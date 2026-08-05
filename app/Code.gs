/**
 * Monitoring Registry Web 管理画面のサーバー側処理。
 *
 * Web アプリ実行時に ActiveSpreadsheet へ依存しないよう、初回設定で
 * スプレッドシート ID とシート名を Script Properties に固定します。
 */

const REGISTRY_HEADERS = Object.freeze([
  'id',
  'enabled',
  'site',
  'preset',
  'url',
  'title',
  'memo',
  'created_at',
  'updated_at',
  'archived',
]);

const LEGACY_HEADERS = Object.freeze([
  'id',
  'enabled',
  'site',
  'preset',
  'url',
  'name',
  'memo',
  'updated_at',
]);

const REGISTRY_PRESETS = Object.freeze({
  'anime-news': {
    label: 'アニメ公式サイトのニュース',
  },
  'comic-valkyrie-work': {
    label: 'コミックヴァルキリー作品',
  },
  'gangan-online-work': {
    label: 'ガンガンONLINE作品',
  },
  'gaugau-work': {
    label: 'がうがうモンスター作品',
  },
  'manga-up-work': {
    label: 'マンガUP!作品',
  },
  'niconico-manga-work': {
    label: 'ニコニコ漫画作品',
  },
  'syosetu-work': {
    label: '小説家になろう作品',
  },
  'syosetu-work-ignore-revised': {
    label: '小説家になろう作品（改稿表示を除外）',
  },
  'yanmaga-work': {
    label: 'ヤンマガWeb作品',
  },
});

const CONFIG_SPREADSHEET_ID = 'SPREADSHEET_ID';
const CONFIG_SHEET_NAME = 'SHEET_NAME';
const DEFAULT_SHEET_NAME = 'Registry';
const LOCK_TIMEOUT_MS = 30000;

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Monitoring Registry')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/**
 * コンテナバインドしたスプレッドシート上の Apps Script エディタで1回実行します。
 * 旧8列なら10列へ移行し、Web実行用にスプレッドシートIDを明示保存します。
 */
function setupForBoundSpreadsheet() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error('スプレッドシートにバインドされた Apps Script から実行してください。');
  }
  const sheet = spreadsheet.getSheetByName(DEFAULT_SHEET_NAME);
  if (!sheet) {
    throw new Error('Registry シートが見つかりません。');
  }

  const migrated = migrateRegistrySchema_(sheet);
  PropertiesService.getScriptProperties().setProperties({
    [CONFIG_SPREADSHEET_ID]: spreadsheet.getId(),
    [CONFIG_SHEET_NAME]: sheet.getName(),
  });

  return {
    spreadsheetId: spreadsheet.getId(),
    sheetName: sheet.getName(),
    migrated: migrated,
    rowCount: Math.max(sheet.getLastRow() - 1, 0),
  };
}

function getInitialData() {
  const entries = readEntries_();
  return {
    entries: entries,
    presets: Object.keys(REGISTRY_PRESETS).map(function (name) {
      return {
        name: name,
        label: REGISTRY_PRESETS[name].label,
      };
    }),
    summary: buildSummary_(entries),
  };
}

function listEntries(query) {
  const options = query || {};
  const needle = normalizeText_(options.search).toLowerCase();
  const status = normalizeText_(options.status) || 'all';

  return readEntries_().filter(function (entry) {
    if (status === 'enabled' && (!entry.enabled || entry.archived)) return false;
    if (status === 'disabled' && (entry.enabled || entry.archived)) return false;
    if (status === 'archived' && !entry.archived) return false;
    if (!needle) return true;
    return [entry.id, entry.title, entry.site, entry.preset, entry.url, entry.memo]
      .join('\n')
      .toLowerCase()
      .includes(needle);
  });
}

function validateEntry(payload) {
  const normalized = normalizeEntryPayload_(payload || {});
  const errors = validateNormalizedEntry_(normalized);
  if (!errors.length) {
    const duplicate = findDuplicateUrl_(normalized.url, normalized.id);
    if (duplicate) errors.push('同じURLが ' + duplicate.id + ' に登録されています。');
  }
  return {
    valid: errors.length === 0,
    errors: errors,
    normalized: normalized,
  };
}

function addEntry(payload) {
  return withRegistryLock_(function () {
    const sheet = getRegistrySheet_();
    const normalized = normalizeEntryPayload_(payload || {});
    assertValidEntry_(normalized);

    const duplicate = findDuplicateUrlInSheet_(sheet, normalized.url, '');
    if (duplicate) {
      throw new Error('同じURLが ' + duplicate.id + ' に登録されています。');
    }

    const now = new Date();
    const id = nextRegistryId_(sheet);
    const row = [
      id,
      normalized.enabled,
      normalized.site,
      normalized.preset,
      normalized.url,
      normalized.title || normalized.url,
      normalized.memo,
      now,
      now,
      false,
    ];
    sheet.appendRow(row);
    const rowNumber = sheet.getLastRow();
    applyRowFormatting_(sheet, rowNumber);
    SpreadsheetApp.flush();
    return getEntryById_(id);
  });
}

function updateEntry(payload) {
  return withRegistryLock_(function () {
    const sheet = getRegistrySheet_();
    const normalized = normalizeEntryPayload_(payload || {});
    if (!normalized.id) throw new Error('更新対象のIDがありません。');
    assertValidEntry_(normalized);

    const location = findEntryRow_(sheet, normalized.id);
    if (!location) throw new Error('対象IDが見つかりません: ' + normalized.id);

    const existing = rowToEntry_(location.values);
    if (existing.url !== normalized.url && payload.confirmUrlChange !== true) {
      throw new Error('URL変更の確認が必要です。画面の警告を確認してから保存してください。');
    }

    const duplicate = findDuplicateUrlInSheet_(sheet, normalized.url, normalized.id);
    if (duplicate) {
      throw new Error('同じURLが ' + duplicate.id + ' に登録されています。');
    }

    const enabled = existing.archived ? false : normalized.enabled;
    // Native Sheets tables reject formatting/data-validation operations on
    // typed columns. Update only the mutable values here; created_at and
    // archived are intentionally left untouched.
    sheet.getRange(location.rowNumber, 2, 1, 6).setValues([[
      enabled,
      normalized.site,
      normalized.preset,
      normalized.url,
      normalized.title || normalized.url,
      normalized.memo,
    ]]);
    sheet.getRange(location.rowNumber, 9).setValue(new Date());
    SpreadsheetApp.flush();
    return getEntryById_(normalized.id);
  });
}

function setEntryEnabled(id, enabled) {
  return withRegistryLock_(function () {
    const sheet = getRegistrySheet_();
    const location = requireEntryRow_(sheet, id);
    const existing = rowToEntry_(location.values);
    if (existing.archived && enabled === true) {
      throw new Error('アーカイブ済みです。先に復元してください。');
    }
    sheet.getRange(location.rowNumber, 2).setValue(enabled === true);
    sheet.getRange(location.rowNumber, 9).setValue(new Date());
    SpreadsheetApp.flush();
    return getEntryById_(id);
  });
}

function archiveEntry(id) {
  return withRegistryLock_(function () {
    const sheet = getRegistrySheet_();
    const location = requireEntryRow_(sheet, id);
    sheet.getRange(location.rowNumber, 2).setValue(false);
    sheet.getRange(location.rowNumber, 9).setValue(new Date());
    sheet.getRange(location.rowNumber, 10).setValue(true);
    SpreadsheetApp.flush();
    return getEntryById_(id);
  });
}

function restoreEntry(id) {
  return withRegistryLock_(function () {
    const sheet = getRegistrySheet_();
    const location = requireEntryRow_(sheet, id);
    const existing = rowToEntry_(location.values);
    const duplicate = findDuplicateUrlInSheet_(sheet, existing.url, id);
    if (duplicate) {
      throw new Error('同じURLが ' + duplicate.id + ' にあるため復元できません。');
    }
    sheet.getRange(location.rowNumber, 2).setValue(true);
    sheet.getRange(location.rowNumber, 9).setValue(new Date());
    sheet.getRange(location.rowNumber, 10).setValue(false);
    SpreadsheetApp.flush();
    return getEntryById_(id);
  });
}

function migrateRegistrySchema_(sheet) {
  const lastColumn = Math.max(sheet.getLastColumn(), LEGACY_HEADERS.length);
  const current = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  const currentLegacy = current.slice(0, LEGACY_HEADERS.length);
  const currentNext = current.slice(0, REGISTRY_HEADERS.length);
  const isLegacy = arraysEqual_(currentLegacy, LEGACY_HEADERS);
  const isNext = arraysEqual_(currentNext, REGISTRY_HEADERS);

  if (!isLegacy && !isNext) {
    throw new Error(
      'Registry の列構成が想定外です。期待値: ' + REGISTRY_HEADERS.join(', ')
    );
  }

  const lastRow = sheet.getLastRow();
  if (isLegacy) {
    if (lastRow > 1) {
      sheet.getRange(2, 8, lastRow - 1, 1).copyTo(
        sheet.getRange(2, 9, lastRow - 1, 1),
        SpreadsheetApp.CopyPasteType.PASTE_NORMAL,
        false
      );
      sheet.getRange(2, 10, lastRow - 1, 1).setValue(false);
    }
    sheet.getRange(1, 1, 1, REGISTRY_HEADERS.length).setValues([REGISTRY_HEADERS]);
  }

  applySheetStructure_(sheet);
  SpreadsheetApp.flush();
  return isLegacy;
}

function applySheetStructure_(sheet) {
  sheet.setFrozenRows(1);
  sheet.getRange('H1').setNote(
    '移行時は旧 updated_at を初期値として複製。新規登録時は作成日時を保存します。'
  );
  sheet.getRange('I1').setNote('管理画面またはシートで最後に編集した日時です。');
  sheet.getRange('J1').setNote(
    'TRUE はアーカイブ済み。アーカイブ時は enabled も FALSE になります。'
  );

  const rows = Math.max(sheet.getLastRow() - 1, 0);
  if (rows > 0) {
    const checkboxRule = buildCheckboxRule_();
    applyCellStructureSafely_(function () {
      sheet.getRange(2, 2, rows, 1).setDataValidation(checkboxRule);
    });
    applyCellStructureSafely_(function () {
      sheet.getRange(2, 10, rows, 1).setDataValidation(checkboxRule);
    });
    applyCellStructureSafely_(function () {
      sheet.getRange(2, 4, rows, 1).setDataValidation(buildPresetRule_());
    });
    applyCellStructureSafely_(function () {
      sheet.getRange(2, 8, rows, 2).setNumberFormat('yyyy-MM-dd HH:mm:ss');
    });
  }

  [120, 90, 170, 220, 320, 260, 240, 150, 150, 100].forEach(function (width, index) {
    sheet.setColumnWidth(index + 1, width);
  });
}

function applyRowFormatting_(sheet, rowNumber) {
  const checkboxRule = buildCheckboxRule_();
  applyCellStructureSafely_(function () {
    sheet.getRange(rowNumber, 2).setDataValidation(checkboxRule);
  });
  applyCellStructureSafely_(function () {
    sheet.getRange(rowNumber, 4).setDataValidation(buildPresetRule_());
  });
  applyCellStructureSafely_(function () {
    sheet.getRange(rowNumber, 10).setDataValidation(checkboxRule);
  });
  applyCellStructureSafely_(function () {
    sheet.getRange(rowNumber, 8, 1, 2).setNumberFormat('yyyy-MM-dd HH:mm:ss');
  });
}

function applyCellStructureSafely_(operation) {
  try {
    operation();
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    if (/typed column|型付きの列|型指定された列/i.test(message)) return;
    throw error;
  }
}

function buildCheckboxRule_() {
  return SpreadsheetApp.newDataValidation().requireCheckbox().build();
}

function buildPresetRule_() {
  return SpreadsheetApp.newDataValidation()
    .requireValueInList(Object.keys(REGISTRY_PRESETS), true)
    .setAllowInvalid(false)
    .build();
}

function getRegistrySheet_() {
  const properties = PropertiesService.getScriptProperties();
  const spreadsheetId = properties.getProperty(CONFIG_SPREADSHEET_ID);
  const sheetName = properties.getProperty(CONFIG_SHEET_NAME) || DEFAULT_SHEET_NAME;
  if (!spreadsheetId) {
    throw new Error('初期設定が未完了です。setupForBoundSpreadsheet を1回実行してください。');
  }

  const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  const sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) throw new Error('設定済みのシートが見つかりません: ' + sheetName);
  assertRegistrySchema_(sheet);
  return sheet;
}

function assertRegistrySchema_(sheet) {
  const headers = sheet
    .getRange(1, 1, 1, REGISTRY_HEADERS.length)
    .getDisplayValues()[0];
  if (!arraysEqual_(headers, REGISTRY_HEADERS)) {
    throw new Error('Registry の列構成が変わっています。setupForBoundSpreadsheet を再確認してください。');
  }
}

function readEntries_() {
  return readEntriesFromSheet_(getRegistrySheet_());
}

function readEntriesFromSheet_(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  return sheet
    .getRange(2, 1, lastRow - 1, REGISTRY_HEADERS.length)
    .getValues()
    .filter(function (row) {
      return normalizeText_(row[0]) !== '';
    })
    .map(rowToEntry_);
}

function rowToEntry_(row) {
  return {
    id: normalizeText_(row[0]),
    enabled: row[1] === true,
    site: normalizeText_(row[2]),
    preset: normalizeText_(row[3]),
    url: normalizeText_(row[4]),
    title: normalizeText_(row[5]) || normalizeText_(row[4]),
    memo: normalizeText_(row[6]),
    createdAt: toIsoString_(row[7]),
    updatedAt: toIsoString_(row[8]),
    archived: row[9] === true,
  };
}

function getEntryById_(id) {
  const match = readEntries_().find(function (entry) {
    return entry.id === id;
  });
  if (!match) throw new Error('保存後の行を取得できませんでした: ' + id);
  return match;
}

function findEntryRow_(sheet, id) {
  const normalizedId = normalizeText_(id);
  const lastRow = sheet.getLastRow();
  if (!normalizedId || lastRow < 2) return null;
  const rows = sheet.getRange(2, 1, lastRow - 1, REGISTRY_HEADERS.length).getValues();
  for (let index = 0; index < rows.length; index += 1) {
    if (normalizeText_(rows[index][0]) === normalizedId) {
      return { rowNumber: index + 2, values: rows[index] };
    }
  }
  return null;
}

function requireEntryRow_(sheet, id) {
  const location = findEntryRow_(sheet, id);
  if (!location) throw new Error('対象IDが見つかりません: ' + id);
  return location;
}

function nextRegistryId_(sheet) {
  const existing = readEntriesFromSheet_(sheet).map(function (entry) {
    return entry.id;
  });
  const used = new Set(existing);
  let maximum = 0;
  existing.forEach(function (id) {
    const match = /^monitor-(\d+)$/.exec(id);
    if (match) maximum = Math.max(maximum, Number(match[1]));
  });
  let candidate;
  do {
    maximum += 1;
    candidate = 'monitor-' + String(maximum).padStart(4, '0');
  } while (used.has(candidate));
  return candidate;
}

function normalizeEntryPayload_(payload) {
  const preset = normalizeText_(payload.preset);
  const url = normalizeText_(payload.url);
  return {
    id: normalizeText_(payload.id),
    enabled: payload.enabled !== false,
    preset: preset,
    site: resolveSite_(url),
    url: url,
    title: normalizeText_(payload.title),
    memo: normalizeText_(payload.memo),
  };
}

function resolveSite_(url) {
  const match = /^https?:\/\/([^/?#:]+)(?::\d+)?(?:[/?#]|$)/i.exec(url);
  const host = match ? match[1].toLowerCase().replace(/^www\./, '') : '';
  if (host === 'syosetu.com' || host.endsWith('.syosetu.com')) return 'syosetu';
  return host;
}

function validateNormalizedEntry_(entry) {
  const errors = [];
  if (!entry.preset || !REGISTRY_PRESETS[entry.preset]) {
    errors.push('プリセットを選択してください。');
  }
  if (!/^https?:\/\/[^\s]+$/i.test(entry.url)) {
    errors.push('URLは http:// または https:// から入力してください。');
  }
  if (entry.title.length > 300) errors.push('タイトルは300文字以内にしてください。');
  if (entry.memo.length > 2000) errors.push('メモは2000文字以内にしてください。');
  return errors;
}

function assertValidEntry_(entry) {
  const errors = validateNormalizedEntry_(entry);
  if (errors.length) throw new Error(errors.join('\n'));
}

function findDuplicateUrl_(url, excludingId) {
  return readEntries_().find(function (entry) {
    return entry.id !== excludingId && canonicalUrl_(entry.url) === canonicalUrl_(url);
  }) || null;
}

function findDuplicateUrlInSheet_(sheet, url, excludingId) {
  return readEntriesFromSheet_(sheet).find(function (entry) {
    return entry.id !== excludingId && canonicalUrl_(entry.url) === canonicalUrl_(url);
  }) || null;
}

function canonicalUrl_(url) {
  return normalizeText_(url).replace(/#.*$/, '').replace(/\/$/, '').toLowerCase();
}

function buildSummary_(entries) {
  return entries.reduce(
    function (summary, entry) {
      summary.total += 1;
      if (entry.archived) summary.archived += 1;
      else if (entry.enabled) summary.enabled += 1;
      else summary.disabled += 1;
      return summary;
    },
    { total: 0, enabled: 0, disabled: 0, archived: 0 }
  );
}

function withRegistryLock_(callback) {
  const lock = LockService.getScriptLock();
  lock.waitLock(LOCK_TIMEOUT_MS);
  try {
    return callback();
  } finally {
    lock.releaseLock();
  }
}

function normalizeText_(value) {
  return value === null || value === undefined ? '' : String(value).trim();
}

function toIsoString_(value) {
  if (!value) return '';
  if (Object.prototype.toString.call(value) === '[object Date]' && !isNaN(value.getTime())) {
    return value.toISOString();
  }
  const parsed = new Date(value);
  return isNaN(parsed.getTime()) ? normalizeText_(value) : parsed.toISOString();
}

function arraysEqual_(left, right) {
  return left.length === right.length && left.every(function (value, index) {
    return value === right[index];
  });
}
