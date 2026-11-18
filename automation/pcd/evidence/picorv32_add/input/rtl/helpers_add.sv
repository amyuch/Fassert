// PCD case-local helper assertions for the ADD control/data path.
//
// These are obligations, not assumptions.  The proof graph may only use a
// named assertion after the engine proves it; a Not Inductive/CEX/timeout is a
// diagnostic, not a premise.

	wire p_add_is_add =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000000) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b000) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);

	// Writeback monitor.  It mirrors the CPU's RVFI write-data registers for
	// the ADD that is currently retiring.
	reg [31:0] p_add_wb_word;
	reg [4:0]  p_add_wb_rd;
	reg        p_add_wb_seen;

	always @(posedge clock) begin
		if (reset) begin
			p_add_wb_word <= 32'd0;
			p_add_wb_rd <= 5'd0;
			p_add_wb_seen <= 1'b0;
		end else begin
			if (wrapper.uut.cpuregs_write && p_add_is_add) begin
				p_add_wb_word <= wrapper.uut.cpuregs_wrdata;
				p_add_wb_rd <= wrapper.uut.latched_rd;
				p_add_wb_seen <= 1'b1;
			end
			if (wrapper.uut.rvfi_valid)
				p_add_wb_seen <= 1'b0;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// Generic ALU writeback mux fact (ADD has latched_stalu == 0).
			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				p_add_wb: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);

			if ($past(!reset) && $past(wrapper.uut.cpuregs_write && p_add_is_add)) begin
				p_add_wb_word_copy: assert(p_add_wb_word ==
					$past(wrapper.uut.cpuregs_wrdata));
			end

			// At retire the writeback monitor describes the retiring ADD.
			if (checker_inst.spec_valid) begin
				p_add_pc_next: assert(rvfi_pc_wdata == rvfi_pc_rdata + 32'd4);
				p_add_wb_seen_fact: assert(p_add_wb_seen);
				p_add_wb_word_fact: assert(wrapper.uut.rvfi_rd_wdata ==
					(p_add_wb_rd != 5'd0 ? p_add_wb_word : 32'd0));
				p_add_wb_rd_fact: assert(wrapper.uut.rvfi_rd_addr == p_add_wb_rd);
				p_add_rvfi_rd: assert(rvfi_rd_addr == rvfi_insn[11:7]);
			end
		end
	end
