import React, { useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Button, Card, DateField, Field, NumberField, RecordField, run, Screen, type Option } from '../../components/ui';
import { api } from '../../lib/api';
import { today } from '../../lib/format';

/** Record cash / bank / UPI money received for an invoice (accountants). */
export default function RegisterPayment() {
  const params = useLocalSearchParams<{ id: string; amount?: string }>();
  const [amount, setAmount] = useState(params.amount ?? '');
  const [journal, setJournal] = useState<Option | null>(null);
  const [paymentDate, setPaymentDate] = useState(today());
  const [memo, setMemo] = useState('');
  const save = async () => {
    const result = await run(() =>
      api.post(`/invoices/${params.id}/payment`, { amount, journal_id: journal?.id, payment_date: paymentDate, memo }),
    );
    if (result) router.back();
  };
  return (
    <Screen footer={<Button title="Register payment" icon="checkmark" onPress={save} disabled={!amount} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: 'Register payment' }} />
      <Card>
        <NumberField label="Amount received" value={amount} onChange={setAmount} required />
        <RecordField label="Paid by (journal)" kind="payment_journals" value={journal} onChange={setJournal} help="Bank or cash. Leave empty for the default journal." />
        <DateField label="Payment date" value={paymentDate} onChange={setPaymentDate} />
        <Field label="Memo / UTR / cheque no." value={memo} onChangeText={setMemo} />
      </Card>
    </Screen>
  );
}
