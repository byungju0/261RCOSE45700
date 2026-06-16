package com.tracker.api.util;

import java.util.Map;

/**
 * Redis에서 읽은 Map(Jackson 파싱 결과 또는 opsForHash().entries() raw 결과)에서
 * 타입 안전하게 필드를 꺼내는 공용 헬퍼. 키/값 타입이 String/Object로 섞여 있어도 동작한다.
 */
public final class RedisFieldExtractor {

    private RedisFieldExtractor() {
    }

    public static String str(Map<?, ?> data, String key) {
        Object v = data.get(key);
        return v == null ? "" : v.toString();
    }

    public static int intValue(Map<?, ?> data, String key) {
        Object v = data.get(key);
        if (v == null) return 0;
        if (v instanceof Number n) return n.intValue();
        try {
            return Integer.parseInt(v.toString());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    public static long longValue(Map<?, ?> data, String key) {
        Object v = data.get(key);
        if (v == null) return 0;
        if (v instanceof Number n) return n.longValue();
        try {
            return Long.parseLong(v.toString());
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
