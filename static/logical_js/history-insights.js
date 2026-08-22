(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.YDLNAS_HISTORY_INSIGHTS = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function() {
    const knownTypes = ['video', 'audio', 'subtitle', 'file'];
    const failedStatuses = ['failed', 'error', 'canceled'];
    const knownFailureCodes = [
        'storage_full', 'storage_permission', 'auth_required', 'rate_limited',
        'format_unavailable', 'unsupported_url', 'network', 'postprocessing',
        'extractor', 'unknown'
    ];

    function isMountedFile(item) {
        return item.source === 'mounted_folder'
            || item.metadata_status === 'missing'
            || item.status === 'file_only';
    }

    function localDayKey(date) {
        return [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, '0'),
            String(date.getDate()).padStart(2, '0')
        ].join('-');
    }

    function validDate(value) {
        const date = new Date(value || '');
        return Number.isNaN(date.getTime()) ? null : date;
    }

    function normalizeFailureCode(item) {
        if (item.status === 'canceled') {
            return 'canceled';
        }
        return knownFailureCodes.indexOf(item.failure_code) >= 0 ? item.failure_code : 'unknown';
    }

    function aggregate(items, nowValue) {
        const suppliedNow = nowValue instanceof Date ? new Date(nowValue.getTime()) : new Date(nowValue || Date.now());
        const now = Number.isNaN(suppliedNow.getTime()) ? new Date() : suppliedNow;
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const days = [];
        const activityByDay = Object.create(null);
        const typeTotals = {
            video: { count: 0, bytes: 0 },
            audio: { count: 0, bytes: 0 },
            subtitle: { count: 0, bytes: 0 },
            file: { count: 0, bytes: 0 }
        };
        const failureCounts = Object.create(null);
        let storedFiles = 0;
        let storedBytes = 0;
        let failedJobs = 0;

        for (let offset = 13; offset >= 0; offset--) {
            const date = new Date(today.getTime());
            date.setDate(today.getDate() - offset);
            const day = { key: localDayKey(date), timestamp: date.getTime(), count: 0 };
            days.push(day);
            activityByDay[day.key] = day;
        }

        (Array.isArray(items) ? items : []).forEach(function(rawItem) {
            const item = rawItem || {};
            const mounted = isMountedFile(item);
            const status = String(item.status || 'unknown').toLowerCase();
            const fileExists = item.file_exists === true;
            const size = Number(item.file_size_bytes || 0);

            if (fileExists) {
                const type = knownTypes.indexOf(item.download_type) >= 0 ? item.download_type : 'file';
                const safeSize = Number.isFinite(size) && size > 0 ? size : 0;
                storedFiles++;
                storedBytes += safeSize;
                typeTotals[type].count++;
                typeTotals[type].bytes += safeSize;
            }

            if (!mounted && status === 'completed') {
                const completedAt = validDate(item.timestamp);
                if (completedAt) {
                    const day = activityByDay[localDayKey(completedAt)];
                    if (day) {
                        day.count++;
                    }
                }
            }

            if (!mounted && failedStatuses.indexOf(status) >= 0) {
                const code = normalizeFailureCode(Object.assign({}, item, { status: status }));
                failedJobs++;
                failureCounts[code] = (failureCounts[code] || 0) + 1;
            }
        });

        const recentCompleted = days.slice(-7).reduce(function(total, day) {
            return total + day.count;
        }, 0);
        const completed14 = days.reduce(function(total, day) {
            return total + day.count;
        }, 0);
        const failureReasons = Object.keys(failureCounts).map(function(code) {
            return { code: code, count: failureCounts[code] };
        }).sort(function(left, right) {
            return right.count - left.count || left.code.localeCompare(right.code);
        });

        return {
            storedFiles: storedFiles,
            storedBytes: storedBytes,
            recentCompleted: recentCompleted,
            failedJobs: failedJobs,
            completed14: completed14,
            activityDays: days,
            typeTotals: typeTotals,
            failureReasons: failureReasons
        };
    }

    return {
        aggregate: aggregate,
        isMountedFile: isMountedFile
    };
});
