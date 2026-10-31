import React, { useState } from 'react';
import { Text, TextInput, View } from 'react-native';

import { api } from '../lib/api';
import { datetime } from '../lib/format';
import { radius, space, useTheme } from '../lib/theme';
import { useApi } from '../lib/useApi';
import { Button, Card, Muted, run, SectionTitle } from './ui';

type Message = { id: number; body: string; date: string; author: string; mine: boolean };

/** Messages of an Odoo document (its chatter), and a box to write one. */
export function Chatter({ model, id, title = 'Messages' }: { model: string; id: number; title?: string }) {
  const t = useTheme();
  const { data, reload } = useApi<{ items: Message[] }>(`/messages/${model}/${id}`);
  const [text, setText] = useState('');
  const send = async () => {
    const ok = await run(() => api.post(`/messages/${model}/${id}`, { body: text }));
    if (ok) {
      setText('');
      reload();
    }
  };
  return (
    <View style={{ gap: space.sm }}>
      <SectionTitle title={title} />
      <Card>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder="Write a message…"
          placeholderTextColor={t.faint}
          multiline
          style={{ color: t.text, minHeight: 60, fontSize: 15, textAlignVertical: 'top', backgroundColor: t.input, borderRadius: radius.md, borderWidth: 1, borderColor: t.border, padding: space.md }}
        />
        <Button title="Send" icon="send" onPress={send} disabled={!text.trim()} />
      </Card>
      {(data?.items ?? []).map((message) => (
        <View
          key={message.id}
          style={{
            alignSelf: message.mine ? 'flex-end' : 'flex-start',
            maxWidth: '88%',
            backgroundColor: message.mine ? t.brandSoft : t.card,
            borderRadius: radius.lg,
            padding: space.md,
            borderWidth: message.mine ? 0 : 1,
            borderColor: t.border,
            gap: 4,
          }}
        >
          <Text style={{ color: t.text, fontSize: 14 }}>{message.body}</Text>
          <Muted style={{ fontSize: 11 }}>
            {message.author} · {datetime(message.date)}
          </Muted>
        </View>
      ))}
      {data && !data.items.length ? <Muted>No messages yet.</Muted> : null}
    </View>
  );
}
