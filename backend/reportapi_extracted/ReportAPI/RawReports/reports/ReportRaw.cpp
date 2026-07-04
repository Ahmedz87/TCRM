//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportRaw.h"
//+------------------------------------------------------------------+
//| Raw Report                                                       |
//+------------------------------------------------------------------+
BOOL CReportRaw::GenerateHTML(const ReportParams* params)
  {
   char   tmp[256]="",num_fmt[32]="";
   int    i,total_count=0,result=TRUE;
   double mul,pips,agents=0,comm=.0,swap=.0,taxes=.0,profit=.0,deposit=.0,withdrawal=.0,credit=.0;
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->trades==NULL || params->trades_total<1) return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- generation
   WriteHeader(m_info.name);
//--- pt styles
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".lots  { mso-number-format:0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
                  ".pt0   {mso-number-format:0;}\n"
                  ".pt1   {mso-number-format:0\\.0;}\n"
                  ".pt2   {mso-number-format:0\\.00;}\n"
                  ".pt3   {mso-number-format:0\\.000;}\n"
                  ".pt4   {mso-number-format:0\\.0000;}\n"
                  ".pt5   {mso-number-format:0\\.00000;}\n"
                  ".pt6   {mso-number-format:0\\.000000;}\n"
                  ".pt7   {mso-number-format:0\\.0000000;}\n"
                  ".pt8   {mso-number-format:0\\.00000000;}\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=99%%>\n");
   fprintf(m_file,"<tr><td colspan=21><font size=2><b>%s</b> for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
   fprintf(m_file,"<tr bgcolor=#c0c0c0 align=right>");
   fprintf(m_file,"<td>Deal</td><td>Login</td><td nowrap>Open Time</td><td>Type</td><td>Symbol</td><td>Volume</td>"
                  "<td nowrap>Open Price</td><td>S/L</td><td>T/P</td><td nowrap>Close Time</td><td nowrap>Close Price</td><td>Reason</td>"
                  "<td>Gateway Order</td><td>Gateway Volume</td><td>Open Price Delta</td><td>Close Price Delta</td>"
                  "<td>Agent</td><td>Commission</td><td>Taxes</td><td>Swap</td><td>Profit</td><td>Points</td><td>Comment</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   TradeRecord *record=params->trades;
   for(i=0;i<params->trades_total;i++,record++)
     {
      if(record->login==0) continue;
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
      else                   fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
      total_count++;
      //--- price format
      if(record->digits<0 || record->digits>8) { COPY_STR(num_fmt,"class=pt4") }
      else StringCchPrintfA(num_fmt,sizeof(num_fmt)-1,"class=pt%d",record->digits);
      //---
      fprintf(m_file,"<td>%d</td>",record->order);
      fprintf(m_file,"<td>%d</td>",record->login);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->open_time,tmp,sizeof(tmp)-1));
      //---
      fprintf(m_file,"<td nowrap>%s</td>",GetCmd(record->cmd));
      if(record->cmd<OP_BALANCE)
        {
         comm  =NormalizeDouble(comm  +record->commission,2);
         taxes =NormalizeDouble(taxes +record->taxes,2);
         swap  =NormalizeDouble(swap  +record->storage,2);
         profit=NormalizeDouble(profit+record->profit,2);
         //---
         COPY_STR(tmp,record->symbol); _strlwr(tmp);
         fprintf(m_file,"<td nowrap>%s</td>",tmp);
         fprintf(m_file,"<td nowrap>%s</td>",ToVolume(record->volume/100.0,tmp,sizeof(tmp)-1));
         ToSymExt(tmp,record->open_price,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         ToSym(tmp,sizeof(tmp)-1,record->sl,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         ToSym(tmp,sizeof(tmp)-1,record->tp,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->close_time,tmp,sizeof(tmp)-1));
         ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
         fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
         fprintf(m_file,"<td nowrap>%s</td>",FormatOrderReason(record->reason,tmp,sizeof(tmp)-1));
         if(record->gw_order>0)
            fprintf(m_file,"<td>%d</td>",record->gw_order);
         else
            fprintf(m_file,"<td></td>");
         if(record->gw_volume>0)
            fprintf(m_file,"<td nowrap>%s</td>",ToVolume(record->gw_volume/100.0,tmp,sizeof(tmp)-1));
         else
            fprintf(m_file,"<td></td>");
         if(record->gw_open_price!=0)
            fprintf(m_file,"<td>%i</td>",record->gw_open_price);
         else
            fprintf(m_file,"<td></td>");
         if(record->gw_close_price!=0)
            fprintf(m_file,"<td>%i</td>",record->gw_close_price);
         else
            fprintf(m_file,"<td></td>");
         if(record->cmd>OP_SELL)
            fprintf(m_file,"<td colspan=6>&nbsp;</td>");
         else
           {
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->commission_agent,2,tmp,sizeof(tmp)-1));
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->commission,2,tmp,sizeof(tmp)-1));
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->taxes     ,2,tmp,sizeof(tmp)-1));
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->storage   ,2,tmp,sizeof(tmp)-1));
            agents=NormalizeDouble(agents+record->commission_agent,2);
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->profit    ,2,tmp,sizeof(tmp)-1));
            mul=Decimals(record->digits);
            if(record->cmd==OP_BUY)
               pips=NormalizeDouble(record->close_price*mul,0)-NormalizeDouble(record->open_price*mul,0);
            else
               pips=NormalizeDouble(record->open_price*mul,0) -NormalizeDouble(record->close_price*mul,0);
            fprintf(m_file,"<td>%d</td>",int(pips));
           }
        }
      else
         if(record->cmd==OP_BALANCE)
           {
            if(record->profit>0) deposit   =NormalizeDouble(deposit   +record->profit,2);
            else                 withdrawal=NormalizeDouble(withdrawal+record->profit,2);
            //---
            fprintf(m_file,"<td nowrap colspan=16 align=left>%s</td>",record->comment);
            fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->profit,2,tmp,sizeof(tmp)-1));
            fprintf(m_file,"<td>&nbsp;</td>");
           }
         else
            if(record->cmd==OP_CREDIT)
              {
               credit=NormalizeDouble(credit+record->profit,2);
               //---
               FormatDateTime(record->close_time,tmp,sizeof(tmp)-1,FALSE);
               fprintf(m_file,"<td nowrap colspan=16 align=left>%s, value date: %s</td>",record->comment,tmp);
               fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->profit,2,tmp,sizeof(tmp)-1));
               fprintf(m_file,"<td>&nbsp;</td>");
              }
      fprintf(m_file,"<td nowrap>%s</td>",record->comment);
      fprintf(m_file,"</tr>\n");
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE; break;
           }
     }
//--- total
   fprintf(m_file,"<tr bgcolor=#c0c0c0 align=right>");
   fprintf(m_file,"<td colspan=16>&nbsp;</td>");
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(agents,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(comm  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(taxes ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(swap  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(profit+deposit+withdrawal,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td>");
   fprintf(m_file,"</tr>\n");
//--- more total
   fprintf(m_file,"<tr align=right><td colspan=19>Profit:</td>");
   fprintf(m_file,"<td colspan=2 nowrap class=money>%s</td>",ToMoney(profit,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td></tr>\n");
   fprintf(m_file,"<tr align=right><td colspan=19>Profit w/o agent commission:</td>");
   fprintf(m_file,"<td colspan=2 nowrap class=money>%s</td>",ToMoney(profit+agents,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td></tr>\n");
   fprintf(m_file,"<tr align=right><td colspan=19>Total broker fee:</td>");
   fprintf(m_file,"<td colspan=2 nowrap class=money>%s</td>",ToMoney(swap+comm,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td></tr>\n");
   fprintf(m_file,"<tr align=right><td colspan=19>Deposit:</td>");
   fprintf(m_file,"<td colspan=2 nowrap class=money>%s</td>",ToMoney(deposit,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td></tr>\n");
   fprintf(m_file,"<tr align=right><td colspan=19>Withdrawal:</td>");
   fprintf(m_file,"<td colspan=2 nowrap class=money>%s</td>",ToMoney(withdrawal,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td></tr>\n");
   fprintf(m_file,"<tr align=right><td colspan=19>Credit:</td>");
   fprintf(m_file,"<td colspan=2 nowrap class=money>%s</td>",ToMoney(credit,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=2>&nbsp;</td></tr>\n");
//---
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportRaw::GenerateCSV(const ReportParams* params)
  {
   char   tmp[256]="";
   int    i,total_count=0,result=TRUE;
   double mul,pips,agents=.0,comm=.0,swap=.0,taxes=.0,profit=.0,deposit=.0,withdrawal=.0,credit=.0;
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->trades==NULL || params->trades_total<1) return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- report header
   fprintf(m_file,"%s for \'%s\'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
   fprintf(m_file,"Deal;Login;Open Time;Type;Symbol;Volume;Open Price;S/L;T/P;Close Time;Close Price;Reason;"
                  "Gateway Order;Gateway Volume;Open Price Delta;Close Price Delta;"
                  "Agent;Commission;Taxes;Swap;Profit;Points;Comment\n");
//--- report rows
   TradeRecord *record=params->trades;
   for(i=0;i<params->trades_total;i++,record++)
     {
      if(record->login<1) continue;
      //---
      fprintf(m_file,"%d;%d;",record->order,record->login);
      FormatDateTime(record->open_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      //---
      fprintf(m_file,"%s;",GetCmd(record->cmd));
      if(record->cmd<OP_BALANCE)
        {
         comm  =NormalizeDouble(comm  +record->commission,2);
         taxes =NormalizeDouble(taxes +record->taxes,2);
         swap  =NormalizeDouble(swap  +record->storage,2);
         profit=NormalizeDouble(profit+record->profit,2);
         //---
         strcpy(tmp,record->symbol); _strlwr(tmp);
         fprintf(m_file,"%s;%.2lf;",tmp,record->volume/100.0);
         ToSymExt(tmp,record->open_price,record->digits); fprintf(m_file,"%s;",tmp);
         ToSym(tmp,sizeof(tmp)-1,record->sl,record->digits); fprintf(m_file,"%s;",tmp);
         ToSym(tmp,sizeof(tmp)-1,record->tp,record->digits); fprintf(m_file,"%s;",tmp);

         FormatDateTime(record->close_time,tmp,sizeof(tmp)-1);
         fprintf(m_file,"%s;",tmp);
         ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
         fprintf(m_file,"%s;",tmp);
         fprintf(m_file,"%s;",FormatOrderReason(record->reason,tmp,sizeof(tmp)-1));
         if(record->gw_order>0)
            fprintf(m_file,"%d;",record->gw_order);
         else
            fprintf(m_file,";");
         if(record->gw_volume>0)
            fprintf(m_file,"%s;",ToVolume(record->gw_volume/100.0,tmp,sizeof(tmp)-1));
         else
            fprintf(m_file,";");
         if(record->gw_open_price!=0)
            fprintf(m_file,"%i;",record->gw_open_price);
         else
            fprintf(m_file,";");
         if(record->gw_close_price!=0)
            fprintf(m_file,"%i;",record->gw_close_price);
         else
            fprintf(m_file,";");
         if(record->cmd>OP_SELL)
            fprintf(m_file,";;;;;;");
         else
           {
            fprintf(m_file,"%.2lf;",record->commission_agent);
            fprintf(m_file,"%.2lf;%.2lf;",record->commission,record->taxes);
            fprintf(m_file,"%.2lf;%.2lf;",record->storage,record->profit);
            agents=NormalizeDouble(agents+record->commission_agent,2);
            mul=Decimals(record->digits);
            if(record->cmd==OP_BUY)
               pips=NormalizeDouble(record->close_price*mul,0)-NormalizeDouble(record->open_price*mul,0);
            else
               pips=NormalizeDouble(record->open_price*mul,0) -NormalizeDouble(record->close_price*mul,0);
            fprintf(m_file,"%d;",int(pips));
           }
        }
      else
         if(record->cmd==OP_BALANCE)
           {
            if(record->profit>0) deposit   =NormalizeDouble(deposit   +record->profit,2);
            else                 withdrawal=NormalizeDouble(withdrawal+record->profit,2);
            //---
            fprintf(m_file,"%s;;;;;;;;;;;;;;;;",record->comment);
            fprintf(m_file,"%.2lf;;",record->profit);
           }
         else
            if(record->cmd==OP_CREDIT)
              {
               credit=NormalizeDouble(credit+record->profit,2);
               //---
               FormatDateTime(record->close_time,tmp,sizeof(tmp)-1,FALSE);
               fprintf(m_file,"%s, value date: %s;;;;;;;;;;;;;;;;",record->comment,tmp);
               fprintf(m_file,"%.2lf;;",record->profit);
              }
      fprintf(m_file,"%s;",record->comment);
      fprintf(m_file,"\n");
      //--- report progress and check cancellation
      total_count++;
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress!=NULL && params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE; break;
           }
     }
//--- total
   fprintf(m_file,";;;;;;;;;;;;;;;;");
   fprintf(m_file,"%.2lf;%.2lf;%.2lf;%.2lf;%.2lf\n",agents,comm,taxes,swap,profit+deposit+withdrawal);
//--- more total
   fprintf(m_file,";;;;;;;;;;;;;;;;;;Profit:;;%.2lf\n",profit);
   fprintf(m_file,";;;;;;;;;;;;;;;;;;Profit w/o agent commission:;;%.2lf\n",profit+agents);
   fprintf(m_file,";;;;;;;;;;;;;;;;;;Total broker fee:;;%.2lf\n",swap+comm);
   fprintf(m_file,";;;;;;;;;;;;;;;;;;Deposit:;;%.2lf\n",deposit);
   fprintf(m_file,";;;;;;;;;;;;;;;;;;Withdrawal:;;%.2lf\n",withdrawal);
   fprintf(m_file,";;;;;;;;;;;;;;;;;;Credit:;;%.2lf\n",credit);
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
