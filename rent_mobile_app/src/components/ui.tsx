import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { absoluteUrl, api, ApiError, authHeaders } from '../lib/api';
import { date as fmtDate, parseDate, toIsoDate, type Tone } from '../lib/format';
import { radius, space, useTheme } from '../lib/theme';
import { useDebounced } from '../lib/useApi';

export type IconName = React.ComponentProps<typeof Ionicons>['name'];

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function Screen({
  children,
  refreshing,
  onRefresh,
  scroll = true,
  padded = true,
  footer,
}: {
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  scroll?: boolean;
  padded?: boolean;
  footer?: React.ReactNode;
}) {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const content = scroll ? (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ padding: padded ? space.lg : 0, paddingBottom: space.xl * 2, gap: space.md }}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={t.brand} /> : undefined}
    >
      {children}
    </ScrollView>
  ) : (
    <View style={{ flex: 1, padding: padded ? space.lg : 0 }}>{children}</View>
  );
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {content}
      {footer ? (
        <View
          style={{
            padding: space.md,
            paddingBottom: Math.max(insets.bottom, space.md),
            backgroundColor: t.card,
            borderTopWidth: StyleSheet.hairlineWidth,
            borderTopColor: t.border,
            flexDirection: 'row',
            gap: space.sm,
          }}
        >
          {footer}
        </View>
      ) : null}
    </KeyboardAvoidingView>
  );
}

export function Card({ children, style, onPress }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void }) {
  const t = useTheme();
  const base: ViewStyle = {
    backgroundColor: t.card,
    borderRadius: radius.lg,
    padding: space.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.border,
    gap: space.sm,
  };
  if (onPress) {
    return (
      <Pressable onPress={onPress} style={({ pressed }) => [base, pressed && { opacity: 0.85 }, style]}>
        {children}
      </Pressable>
    );
  }
  return <View style={[base, style]}>{children}</View>;
}

export function SectionTitle({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: space.sm }}>
      <Text style={{ color: t.muted, fontSize: 13, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase' }}>{title}</Text>
      {action ? (
        <Pressable onPress={onAction} hitSlop={10}>
          <Text style={{ color: t.brand, fontWeight: '600' }}>{action}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function Title({ children, sub }: { children: React.ReactNode; sub?: string }) {
  const t = useTheme();
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: t.text, fontSize: 22, fontWeight: '800' }}>{children}</Text>
      {sub ? <Text style={{ color: t.muted, fontSize: 14 }}>{sub}</Text> : null}
    </View>
  );
}

export function Muted({ children, style }: { children: React.ReactNode; style?: any }) {
  const t = useTheme();
  return <Text style={[{ color: t.muted, fontSize: 13 }, style]}>{children}</Text>;
}

export function Body({ children, style }: { children: React.ReactNode; style?: any }) {
  const t = useTheme();
  return <Text style={[{ color: t.text, fontSize: 15, lineHeight: 21 }, style]}>{children}</Text>;
}

export function Row({ label, value, strong, tone }: { label: string; value?: React.ReactNode; strong?: boolean; tone?: Tone }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.md, paddingVertical: 3 }}>
      <Text style={{ color: t.muted, fontSize: 14, flexShrink: 0 }}>{label}</Text>
      {typeof value === 'string' || typeof value === 'number' || value === undefined || value === null ? (
        <Text
          style={{
            color: tone ? t.tones[tone].fg : t.text,
            fontSize: 14,
            fontWeight: strong ? '700' : '500',
            flexShrink: 1,
            textAlign: 'right',
          }}
        >
          {value === undefined || value === null || value === '' ? '—' : String(value)}
        </Text>
      ) : (
        value
      )}
    </View>
  );
}

export function Divider() {
  const t = useTheme();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: t.border, marginVertical: space.xs }} />;
}

export function Badge({ label, tone = 'neutral', icon }: { label: string; tone?: Tone; icon?: IconName }) {
  const t = useTheme();
  const c = t.tones[tone];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: c.bg, paddingHorizontal: 9, paddingVertical: 3, borderRadius: radius.pill, alignSelf: 'flex-start' }}>
      {icon ? <Ionicons name={icon} size={12} color={c.fg} /> : null}
      <Text style={{ color: c.fg, fontSize: 12, fontWeight: '700' }}>{label}</Text>
    </View>
  );
}

export function Progress({ value, tone = 'brand' }: { value: number; tone?: Tone }) {
  const t = useTheme();
  return (
    <View style={{ height: 8, backgroundColor: t.tones.neutral.bg, borderRadius: 4, overflow: 'hidden' }}>
      <View style={{ width: `${Math.min(Math.max(value, 0), 100)}%`, height: '100%', backgroundColor: t.tones[tone].fg, borderRadius: 4 }} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

export function Button({
  title,
  onPress,
  variant = 'primary',
  icon,
  loading,
  disabled,
  style,
  tone,
}: {
  title: string;
  onPress: () => unknown;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  tone?: Tone;
}) {
  const t = useTheme();
  const [busy, setBusy] = useState(false);
  const colors = {
    primary: { bg: t.brand, fg: t.onBrand, border: t.brand },
    secondary: { bg: t.card, fg: t.text, border: t.border },
    ghost: { bg: 'transparent', fg: t.brand, border: 'transparent' },
    danger: { bg: t.tones.danger.bg, fg: t.tones.danger.fg, border: t.tones.danger.bg },
  }[variant];
  if (tone) {
    colors.bg = t.tones[tone].bg;
    colors.fg = t.tones[tone].fg;
    colors.border = t.tones[tone].bg;
  }
  const isLoading = loading || busy;
  return (
    <Pressable
      disabled={disabled || isLoading}
      onPress={async () => {
        const result = onPress();
        if (result instanceof Promise) {
          setBusy(true);
          try {
            await result;
          } finally {
            setBusy(false);
          }
        }
      }}
      style={({ pressed }) => [
        {
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          minHeight: 46,
          paddingHorizontal: space.lg,
          borderRadius: radius.md,
          backgroundColor: colors.bg,
          borderWidth: 1,
          borderColor: colors.border,
          opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      {isLoading ? <ActivityIndicator color={colors.fg} /> : icon ? <Ionicons name={icon} size={18} color={colors.fg} /> : null}
      <Text style={{ color: colors.fg, fontWeight: '700', fontSize: 15 }}>{title}</Text>
    </Pressable>
  );
}

export function Fab({ icon = 'add', onPress, label }: { icon?: IconName; onPress: () => void; label?: string }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityLabel={label}
      style={({ pressed }) => ({
        position: 'absolute',
        right: space.lg,
        bottom: space.lg,
        backgroundColor: t.brand,
        borderRadius: radius.pill,
        paddingHorizontal: label ? 18 : 0,
        width: label ? undefined : 56,
        height: 56,
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'row',
        gap: 6,
        elevation: 4,
        shadowColor: '#000',
        shadowOpacity: 0.2,
        shadowRadius: 8,
        shadowOffset: { width: 0, height: 3 },
        opacity: pressed ? 0.9 : 1,
      })}
    >
      <Ionicons name={icon} size={24} color={t.onBrand} />
      {label ? <Text style={{ color: t.onBrand, fontWeight: '700' }}>{label}</Text> : null}
    </Pressable>
  );
}

export function IconButton({ icon, onPress, label }: { icon: IconName; onPress: () => void; label?: string }) {
  const t = useTheme();
  return (
    <Pressable onPress={onPress} hitSlop={10} accessibilityLabel={label} style={{ padding: 4 }}>
      <Ionicons name={icon} size={22} color={t.brand} />
    </Pressable>
  );
}

/** Ask for confirmation, run the action and report API errors. */
export function confirmAction(title: string, message: string, action: () => Promise<unknown>, confirmLabel = 'Confirm') {
  return new Promise<void>((resolve) => {
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve() },
      {
        text: confirmLabel,
        style: /delete|cancel|terminate/i.test(confirmLabel) ? 'destructive' : 'default',
        onPress: async () => {
          await run(action);
          resolve();
        },
      },
    ]);
  });
}

/** Run an API call and show its error in an alert. Returns the result, or undefined on error. */
export async function run<T>(action: () => Promise<T>): Promise<T | undefined> {
  try {
    return await action();
  } catch (error) {
    Alert.alert('Could not complete', error instanceof Error ? error.message : String(error));
    return undefined;
  }
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

export function Loading() {
  const t = useTheme();
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl, backgroundColor: t.bg }}>
      <ActivityIndicator size="large" color={t.brand} />
    </View>
  );
}

export function ErrorView({ error, onRetry }: { error: ApiError | Error | null; onRetry?: () => void }) {
  const t = useTheme();
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl, gap: space.md, backgroundColor: t.bg }}>
      <Ionicons name={(error as ApiError)?.status === 0 ? 'cloud-offline-outline' : 'alert-circle-outline'} size={48} color={t.faint} />
      <Text style={{ color: t.text, textAlign: 'center', fontSize: 15 }}>{error?.message ?? 'Something went wrong.'}</Text>
      {onRetry ? <Button title="Try again" variant="secondary" icon="refresh" onPress={onRetry} /> : null}
    </View>
  );
}

export function Empty({ icon = 'file-tray-outline', title, text }: { icon?: IconName; title: string; text?: string }) {
  const t = useTheme();
  return (
    <View style={{ alignItems: 'center', padding: space.xl, gap: space.sm }}>
      <Ionicons name={icon} size={44} color={t.faint} />
      <Text style={{ color: t.text, fontWeight: '700', fontSize: 16 }}>{title}</Text>
      {text ? <Text style={{ color: t.muted, textAlign: 'center' }}>{text}</Text> : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Lists
// ---------------------------------------------------------------------------

export function ListItem({
  title,
  subtitle,
  meta,
  right,
  badge,
  icon,
  image,
  onPress,
}: {
  title: string;
  subtitle?: string;
  meta?: string;
  right?: string;
  badge?: { label: string; tone?: Tone };
  icon?: IconName;
  image?: string | null;
  onPress?: () => void;
}) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: space.md,
        backgroundColor: pressed ? t.cardAlt : t.card,
        padding: space.md,
        borderRadius: radius.md,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: t.border,
      })}
    >
      {image ? (
        <AuthImage path={image} style={{ width: 46, height: 46, borderRadius: radius.sm }} />
      ) : icon ? (
        <View style={{ width: 42, height: 42, borderRadius: radius.sm, backgroundColor: t.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={20} color={t.brand} />
        </View>
      ) : null}
      <View style={{ flex: 1, gap: 3 }}>
        <Text numberOfLines={1} style={{ color: t.text, fontSize: 15, fontWeight: '700' }}>{title}</Text>
        {subtitle ? <Text numberOfLines={1} style={{ color: t.muted, fontSize: 13 }}>{subtitle}</Text> : null}
        {meta ? <Text numberOfLines={1} style={{ color: t.faint, fontSize: 12 }}>{meta}</Text> : null}
      </View>
      <View style={{ alignItems: 'flex-end', gap: 4 }}>
        {right ? <Text style={{ color: t.text, fontWeight: '700', fontSize: 14 }}>{right}</Text> : null}
        {badge ? <Badge label={badge.label} tone={badge.tone} /> : null}
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={18} color={t.faint} /> : null}
    </Pressable>
  );
}

export function SearchBar({ value, onChange, placeholder = 'Search' }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: t.input, borderRadius: radius.md, borderWidth: 1, borderColor: t.border, paddingHorizontal: space.md }}>
      <Ionicons name="search" size={18} color={t.faint} />
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={t.faint}
        style={{ flex: 1, color: t.text, paddingVertical: 10, fontSize: 15 }}
        autoCorrect={false}
        returnKeyType="search"
      />
      {value ? (
        <Pressable onPress={() => onChange('')} hitSlop={8}>
          <Ionicons name="close-circle" size={18} color={t.faint} />
        </Pressable>
      ) : null}
    </View>
  );
}

export function Chips<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  const t = useTheme();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: radius.pill, backgroundColor: active ? t.brand : t.card, borderWidth: 1, borderColor: active ? t.brand : t.border }}
          >
            <Text style={{ color: active ? t.onBrand : t.text, fontWeight: '600', fontSize: 13 }}>{option.label}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

/** Searchable, filterable, paginated list screen body. */
export function ListScreen<T>({
  header,
  items,
  total,
  renderItem,
  loading,
  error,
  refreshing,
  onRefresh,
  onEndReached,
  loadingMore,
  empty,
  fab,
}: {
  header?: React.ReactNode;
  items: T[];
  total: number;
  renderItem: (item: T) => React.ReactElement;
  loading: boolean;
  error: ApiError | null;
  refreshing: boolean;
  onRefresh: () => void;
  onEndReached?: () => void;
  loadingMore?: boolean;
  empty: { title: string; text?: string; icon?: IconName };
  fab?: React.ReactNode;
}) {
  const t = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <FlatList
        data={items}
        keyExtractor={(item: any, index) => String(item.id ?? index)}
        renderItem={({ item }) => renderItem(item)}
        contentContainerStyle={{ padding: space.lg, gap: space.sm, paddingBottom: 96 }}
        ListHeaderComponent={header ? <View style={{ gap: space.md, marginBottom: space.sm }}>{header}</View> : undefined}
        ListEmptyComponent={loading ? <ActivityIndicator color={t.brand} style={{ marginTop: 40 }} /> : error ? <ErrorView error={error} onRetry={onRefresh} /> : <Empty {...empty} />}
        ListFooterComponent={
          items.length ? (
            <Text style={{ color: t.faint, textAlign: 'center', marginTop: space.sm, fontSize: 12 }}>
              {loadingMore ? 'Loading…' : `${items.length} of ${total}`}
            </Text>
          ) : undefined
        }
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={t.brand} />}
        onEndReached={onEndReached}
        onEndReachedThreshold={0.4}
        keyboardShouldPersistTaps="handled"
      />
      {fab}
    </View>
  );
}

// ---------------------------------------------------------------------------
// KPIs and charts
// ---------------------------------------------------------------------------

export function Kpi({ label, value, hint, icon, tone = 'brand', onPress }: { label: string; value: string; hint?: string; icon?: IconName; tone?: Tone; onPress?: () => void }) {
  const t = useTheme();
  return (
    <Card style={{ flex: 1, minWidth: '45%', gap: 6, padding: space.md }} onPress={onPress}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        {icon ? (
          <View style={{ backgroundColor: t.tones[tone].bg, borderRadius: radius.sm, padding: 5 }}>
            <Ionicons name={icon} size={14} color={t.tones[tone].fg} />
          </View>
        ) : null}
        <Text numberOfLines={1} style={{ color: t.muted, fontSize: 12, fontWeight: '600', flex: 1 }}>{label}</Text>
      </View>
      <Text numberOfLines={1} adjustsFontSizeToFit style={{ color: t.text, fontSize: 20, fontWeight: '800' }}>{value}</Text>
      {hint ? <Text numberOfLines={2} style={{ color: t.faint, fontSize: 11 }}>{hint}</Text> : null}
    </Card>
  );
}

export function BarChart({ data, format, series }: {
  data: { label: string; values: number[] }[];
  format: (v: number) => string;
  series: { label: string; tone: Tone }[];
}) {
  const t = useTheme();
  const max = Math.max(1, ...data.flatMap((d) => d.values));
  return (
    <View style={{ gap: space.sm }}>
      <View style={{ flexDirection: 'row', gap: space.md }}>
        {series.map((s) => (
          <View key={s.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: t.tones[s.tone].fg }} />
            <Text style={{ color: t.muted, fontSize: 12 }}>{s.label}</Text>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 130, gap: 4 }}>
        {data.map((d, i) => (
          <View key={i} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
            <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 110, gap: 2 }}>
              {d.values.map((v, j) => (
                <View
                  key={j}
                  accessibilityLabel={`${d.label} ${series[j]?.label}: ${format(v)}`}
                  style={{ width: series.length > 1 ? 7 : 14, height: Math.max(2, (110 * v) / max), backgroundColor: t.tones[series[j]?.tone ?? 'brand'].fg, borderRadius: 3, opacity: v ? 1 : 0.25 }}
                />
              ))}
            </View>
            <Text style={{ color: t.faint, fontSize: 10 }}>{d.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Forms
// ---------------------------------------------------------------------------

function FieldShell({ label, required, children, help }: { label: string; required?: boolean; children: React.ReactNode; help?: string }) {
  const t = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ color: t.muted, fontSize: 13, fontWeight: '600' }}>
        {label}
        {required ? <Text style={{ color: t.tones.danger.fg }}> *</Text> : null}
      </Text>
      {children}
      {help ? <Text style={{ color: t.faint, fontSize: 12 }}>{help}</Text> : null}
    </View>
  );
}

export function Field({ label, required, help, ...props }: TextInputProps & { label: string; required?: boolean; help?: string }) {
  const t = useTheme();
  return (
    <FieldShell label={label} required={required} help={help}>
      <TextInput
        placeholderTextColor={t.faint}
        {...props}
        style={[
          { backgroundColor: t.input, color: t.text, borderWidth: 1, borderColor: t.border, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 11, fontSize: 15 },
          props.multiline && { minHeight: 96, textAlignVertical: 'top' },
          props.style,
        ]}
      />
    </FieldShell>
  );
}

export function NumberField({ value, onChange, ...props }: { label: string; value: number | string | null | undefined; onChange: (v: string) => void; required?: boolean; help?: string; placeholder?: string }) {
  return (
    <Field
      {...props}
      value={value === null || value === undefined ? '' : String(value)}
      onChangeText={(text) => onChange(text.replace(/[^0-9.,-]/g, '').replace(',', '.'))}
      keyboardType="decimal-pad"
    />
  );
}

export function SwitchField({ label, value, onChange, help }: { label: string; value: boolean; onChange: (v: boolean) => void; help?: string }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md, paddingVertical: 4 }}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: t.text, fontSize: 15 }}>{label}</Text>
        {help ? <Text style={{ color: t.faint, fontSize: 12 }}>{help}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: t.brand }} />
    </View>
  );
}

export type Option = { id: number | string; name: string; [key: string]: any };

function PickerModal({ visible, title, options, loading, onSearch, onPick, onClose }: {
  visible: boolean;
  title: string;
  options: Option[];
  loading?: boolean;
  onSearch?: (text: string) => void;
  onPick: (o: Option | null) => void;
  onClose: () => void;
}) {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const [search, setSearchText] = useState('');
  const setSearch = (text: string) => {
    setSearchText(text);
    onSearch?.(text);
  };
  const close = () => {
    setSearch('');
    onClose();
  };
  const shown = onSearch ? options : options.filter((o) => o.name.toLowerCase().includes(search.toLowerCase()));
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={close}>
      <View style={{ flex: 1, backgroundColor: t.bg, paddingTop: Platform.OS === 'android' ? insets.top : 0 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: space.lg }}>
          <Text style={{ color: t.text, fontSize: 18, fontWeight: '800' }}>{title}</Text>
          <Pressable onPress={close} hitSlop={10}>
            <Text style={{ color: t.brand, fontWeight: '700', fontSize: 16 }}>Close</Text>
          </Pressable>
        </View>
        {options.length > 8 || onSearch ? (
          <View style={{ paddingHorizontal: space.lg, paddingBottom: space.sm }}>
            <SearchBar value={search} onChange={setSearch} />
          </View>
        ) : null}
        <FlatList
          data={shown}
          keyExtractor={(o) => String(o.id)}
          contentContainerStyle={{ padding: space.lg, gap: space.sm, paddingBottom: insets.bottom + space.xl }}
          ListEmptyComponent={loading ? <ActivityIndicator color={t.brand} /> : <Empty title="Nothing found" />}
          keyboardShouldPersistTaps="handled"
          renderItem={({ item }) => (
            <Pressable
              onPress={() => {
                setSearch('');
                onPick(item);
              }}
              style={({ pressed }) => ({ padding: space.md, borderRadius: radius.md, backgroundColor: pressed ? t.cardAlt : t.card, borderWidth: StyleSheet.hairlineWidth, borderColor: t.border })}
            >
              <Text style={{ color: t.text, fontSize: 15 }}>{item.name}</Text>
            </Pressable>
          )}
        />
      </View>
    </Modal>
  );
}

function SelectButton({ text, placeholder, onPress, onClear }: { text?: string; placeholder: string; onPress: () => void; onClear?: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: t.input, borderWidth: 1, borderColor: t.border, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, gap: 8 }}
    >
      <Text style={{ flex: 1, color: text ? t.text : t.faint, fontSize: 15 }} numberOfLines={1}>{text || placeholder}</Text>
      {text && onClear ? (
        <Pressable onPress={onClear} hitSlop={8}>
          <Ionicons name="close-circle" size={18} color={t.faint} />
        </Pressable>
      ) : (
        <Ionicons name="chevron-down" size={18} color={t.faint} />
      )}
    </Pressable>
  );
}

/** Pick one value among static options (selection fields). */
export function SelectField({ label, value, options, onChange, required, help, placeholder = 'Select…' }: {
  label: string;
  value: string | null | undefined;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  required?: boolean;
  help?: string;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  return (
    <FieldShell label={label} required={required} help={help}>
      <SelectButton text={current?.label} placeholder={placeholder} onPress={() => setOpen(true)} />
      <PickerModal
        visible={open}
        title={label}
        options={options.map((o) => ({ id: o.value, name: o.label }))}
        onPick={(o) => {
          if (o) onChange(String(o.id));
          setOpen(false);
        }}
        onClose={() => setOpen(false)}
      />
    </FieldShell>
  );
}

/** Pick a record from /options/<kind> (many2one fields). */
export function RecordField({ label, kind, value, onChange, required, help, params, placeholder = 'Select…', clearable = true }: {
  label: string;
  kind: string;
  value: Option | null | undefined;
  onChange: (v: Option | null) => void;
  required?: boolean;
  help?: string;
  params?: Record<string, string | number | undefined>;
  placeholder?: string;
  clearable?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [result, setResult] = useState<{ key: string; items: Option[] } | null>(null);
  const debounced = useDebounced(search);
  const query = useMemo(
    () =>
      Object.entries({ ...params, search: debounced })
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
        .join('&'),
    [params, debounced],
  );
  const key = `${kind}?${query}`;
  useEffect(() => {
    if (!open) return;
    let alive = true;
    api
      .get<{ items: Option[] }>(`/options/${key}`)
      .then((r) => alive && setResult({ key, items: r.items }))
      .catch(() => alive && setResult({ key, items: [] }));
    return () => {
      alive = false;
    };
  }, [open, key]);
  const options = result?.items ?? [];
  const loading = open && result?.key !== key;
  return (
    <FieldShell label={label} required={required} help={help}>
      <SelectButton text={value?.name} placeholder={placeholder} onPress={() => setOpen(true)} onClear={clearable ? () => onChange(null) : undefined} />
      <PickerModal
        visible={open}
        title={label}
        options={options}
        loading={loading}
        onSearch={setSearch}
        onPick={(o) => {
          onChange(o);
          setOpen(false);
        }}
        onClose={() => setOpen(false)}
      />
    </FieldShell>
  );
}

export function DateField({ label, value, onChange, required, help }: { label: string; value: string | null | undefined; onChange: (v: string) => void; required?: boolean; help?: string }) {
  const t = useTheme();
  const [open, setOpen] = useState(false);
  const current = parseDate(value) ?? new Date();
  const show = () => {
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: current,
        mode: 'date',
        onChange: (event, picked) => {
          if (event.type === 'set' && picked) onChange(toIsoDate(picked));
        },
      });
    } else {
      setOpen(true);
    }
  };
  return (
    <FieldShell label={label} required={required} help={help}>
      <SelectButton text={value ? fmtDate(value) : undefined} placeholder="Pick a date" onPress={show} />
      {Platform.OS !== 'android' ? (
        <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
          <Pressable style={{ flex: 1, backgroundColor: '#0006', justifyContent: 'center', padding: space.lg }} onPress={() => setOpen(false)}>
            <Pressable style={{ backgroundColor: t.card, borderRadius: radius.lg, padding: space.md }}>
              <DateTimePicker
                value={current}
                mode="date"
                display="inline"
                onChange={(_event, picked) => {
                  if (picked) onChange(toIsoDate(picked));
                }}
              />
              <Button title="Done" onPress={() => setOpen(false)} />
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}
    </FieldShell>
  );
}

// ---------------------------------------------------------------------------
// Images
// ---------------------------------------------------------------------------

export function AuthImage({ path, style }: { path: string; style?: any }) {
  return (
    <Image
      source={{ uri: absoluteUrl(path), headers: authHeaders() }}
      style={style}
      contentFit="cover"
      transition={150}
    />
  );
}

export type Photo = { uri: string; base64: string };

export async function pickPhoto(source: 'camera' | 'library'): Promise<Photo | null> {
  const permission = source === 'camera'
    ? await ImagePicker.requestCameraPermissionsAsync()
    : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) {
    Alert.alert('Permission needed', `Allow access to the ${source === 'camera' ? 'camera' : 'photos'} in your phone settings.`);
    return null;
  }
  const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.6, base64: true, allowsEditing: false };
  const result = source === 'camera' ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
  if (result.canceled || !result.assets?.[0]?.base64) return null;
  return { uri: result.assets[0].uri, base64: result.assets[0].base64 };
}

export function choosePhoto(onPhoto: (photo: Photo) => void) {
  Alert.alert('Add photo', undefined, [
    { text: 'Take photo', onPress: async () => { const p = await pickPhoto('camera'); if (p) onPhoto(p); } },
    { text: 'Choose from gallery', onPress: async () => { const p = await pickPhoto('library'); if (p) onPhoto(p); } },
    { text: 'Cancel', style: 'cancel' },
  ]);
}

export function PhotoStrip({ photos, onAdd, onRemove, max = 5 }: { photos: Photo[]; onAdd?: () => void; onRemove?: (index: number) => void; max?: number }) {
  const t = useTheme();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
      {photos.map((photo, index) => (
        <View key={photo.uri}>
          <Image source={{ uri: photo.uri }} style={{ width: 84, height: 84, borderRadius: radius.md }} />
          {onRemove ? (
            <Pressable onPress={() => onRemove(index)} style={{ position: 'absolute', top: 4, right: 4, backgroundColor: '#000a', borderRadius: 12 }}>
              <Ionicons name="close" size={18} color="#fff" />
            </Pressable>
          ) : null}
        </View>
      ))}
      {onAdd && photos.length < max ? (
        <Pressable
          onPress={onAdd}
          style={{ width: 84, height: 84, borderRadius: radius.md, borderWidth: 1.5, borderStyle: 'dashed', borderColor: t.border, alignItems: 'center', justifyContent: 'center', gap: 2 }}
        >
          <Ionicons name="camera-outline" size={24} color={t.brand} />
          <Text style={{ color: t.brand, fontSize: 11, fontWeight: '600' }}>Add</Text>
        </Pressable>
      ) : null}
    </ScrollView>
  );
}
